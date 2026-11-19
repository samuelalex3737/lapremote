"""Linux media sessions through playerctl (MPRIS).

``playerctl --all-players --follow metadata --format ...`` prints a line whenever a
player's metadata or status changes. Fields are separated by the ASCII unit
separator so titles containing ``|`` or tabs are safe.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from lapremote.logging_setup import get_logger, log_event
from lapremote.media.base import (
    MediaBackend,
    MediaCommand,
    SessionSnapshot,
    friendly_app_name,
    now_ms,
    thumbnail_jpeg,
)

log = get_logger("media.linux")

SEP = "\x1f"
FIELDS = (
    "playerName",
    "status",
    "position",
    "mpris:length",
    "xesam:title",
    "xesam:artist",
    "xesam:album",
    "mpris:artUrl",
)
FORMAT = SEP.join("{{" + f + "}}" for f in FIELDS)
COMMANDS: dict[MediaCommand, str] = {
    "toggle": "play-pause",
    "play": "play",
    "pause": "pause",
    "next": "next",
    "prev": "previous",
}
PRUNE_SECONDS = 2.0
MAX_ART_BYTES = 8_000_000


def _micros(value: str) -> float | None:
    try:
        return int(value) / 1_000_000
    except ValueError:
        return None


def parse_line(line: str) -> dict[str, str] | None:
    parts = line.rstrip("\n").split(SEP)
    if len(parts) != len(FIELDS) or not parts[0]:
        return None
    return dict(zip(FIELDS, parts, strict=True))


def read_local_art(url: str) -> bytes | None:
    """Only file:// artwork is read. Remote URLs are never fetched."""
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    path = Path(url2pathname(parsed.path))
    try:
        if not path.is_file() or path.stat().st_size > MAX_ART_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None


def snapshot_from_fields(fields: dict[str, str], artwork: bytes | None) -> SessionSnapshot:
    name = fields["playerName"]
    status = fields["status"].lower()
    duration = _micros(fields["mpris:length"])
    snapshot = SessionSnapshot(
        id=name,
        app_id=name,
        app_name=friendly_app_name(name),
        title=fields["xesam:title"],
        artist=fields["xesam:artist"],
        album=fields["xesam:album"],
        status="playing" if status == "playing" else "paused" if status == "paused" else "stopped",
        position=_micros(fields["position"]),
        duration=duration,
        rate=1.0,
        can_seek=duration is not None and duration > 0,
        can_next=True,
        can_prev=True,
        updated_at=now_ms(),
    )
    return snapshot.with_artwork(artwork)


class PlayerctlBackend(MediaBackend):
    name = "playerctl"

    def __init__(self, executable: str) -> None:
        super().__init__()
        self._exe = executable
        self._proc: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._sessions: dict[str, SessionSnapshot] = {}
        self._art_urls: dict[str, str] = {}

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            self._exe,
            "--all-players",
            "--follow",
            "metadata",
            "--format",
            FORMAT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        loop = asyncio.get_running_loop()
        self._tasks = [loop.create_task(self._read()), loop.create_task(self._prune())]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            with contextlib.suppress(ProcessLookupError):
                await self._proc.wait()

    async def _read(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                log_event(log, "follow_ended", level=30, code=proc.returncode)
                return
            fields = parse_line(raw.decode("utf-8", "replace"))
            if fields is None:
                continue
            await self.apply(fields)

    async def apply(self, fields: dict[str, str]) -> None:
        name = fields["playerName"]
        url = fields["mpris:artUrl"]
        previous = self._sessions.get(name)
        artwork = previous.artwork_jpeg if previous is not None else None
        if self._art_urls.get(name) != url:
            self._art_urls[name] = url
            raw = await asyncio.to_thread(read_local_art, url) if url else None
            artwork = await asyncio.to_thread(thumbnail_jpeg, raw) if raw else None
        self._sessions[name] = snapshot_from_fields(fields, artwork)
        self._notify()

    async def _players(self) -> set[str] | None:
        proc = await asyncio.create_subprocess_exec(
            self._exe,
            "--list-all",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        if proc.returncode not in (0, 1):
            return None
        return {
            line.strip() for line in out.decode("utf-8", "replace").splitlines() if line.strip()
        }

    async def _prune(self) -> None:
        while True:
            await asyncio.sleep(PRUNE_SECONDS)
            players = await self._players()
            if players is None:
                continue
            gone = set(self._sessions) - players
            for name in gone:
                self._sessions.pop(name, None)
                self._art_urls.pop(name, None)
            if gone:
                self._notify()

    def list_sessions(self) -> list[SessionSnapshot]:
        return list(self._sessions.values())

    def system_current_id(self) -> str | None:
        return None

    async def _run(self, player: str, *args: str) -> bool:
        if player not in self._sessions:
            return False
        proc = await asyncio.create_subprocess_exec(
            self._exe,
            "--player",
            player,
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await proc.wait() == 0

    async def command(self, session_id: str, action: MediaCommand) -> bool:
        return await self._run(session_id, COMMANDS[action])

    async def seek_to(self, session_id: str, seconds: float) -> bool:
        # The player name must be a known session and the position is a number we format.
        return await self._run(session_id, "position", f"{max(0.0, seconds):.3f}")

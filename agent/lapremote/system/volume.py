"""System output volume: get/set/step/mute per OS, pushed to phones as volume.state.

Windows uses pycaw (Core Audio), macOS uses osascript, Linux uses pactl. When no
backend works, volume.step and volume.mute fall back to the OS volume keys.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import shutil
import time
from typing import Any, Protocol

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.media.keys_fallback import MediaKeys
from lapremote.protocol import OsName, VolumeMute, VolumeSet, VolumeState, VolumeStep
from lapremote.router import ActionError

log = get_logger("volume")

POLL_SECONDS = 0.5
REACQUIRE_SECONDS = 5.0


class VolumeError(Exception):
    """The volume could not be read or changed."""


class VolumeBackend(Protocol):
    name: str

    async def get(self) -> tuple[int, bool]: ...
    async def set_level(self, level: int) -> None: ...
    async def set_muted(self, muted: bool) -> None: ...


class WindowsVolume:
    """Core Audio endpoint volume of the default output device (re-read every few seconds)."""

    name = "pycaw"

    def __init__(self) -> None:
        self._endpoint: Any = None
        self._acquired = 0.0

    def _ep(self) -> Any:
        if self._endpoint is None or time.monotonic() - self._acquired > REACQUIRE_SECONDS:
            from pycaw.pycaw import AudioUtilities  # noqa: PLC0415 - Windows only

            self._endpoint = AudioUtilities.GetSpeakers().EndpointVolume
            self._acquired = time.monotonic()
        return self._endpoint

    def _call(self, fn: str, *args: object) -> Any:
        try:
            return getattr(self._ep(), fn)(*args)
        except (OSError, AttributeError) as exc:
            self._endpoint = None
            raise VolumeError(str(exc)) from exc

    async def get(self) -> tuple[int, bool]:
        level = round(float(self._call("GetMasterVolumeLevelScalar")) * 100)
        return level, bool(self._call("GetMute"))

    async def set_level(self, level: int) -> None:
        self._call("SetMasterVolumeLevelScalar", level / 100, None)

    async def set_muted(self, muted: bool) -> None:
        self._call("SetMute", int(muted), None)


async def _run(exe: str, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        exe, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        msg = f"{exe} exited with {proc.returncode}"
        raise VolumeError(msg)
    return out.decode("utf-8", "replace")


class MacVolume:
    name = "osascript"

    def __init__(self, exe: str) -> None:
        self._exe = exe

    async def get(self) -> tuple[int, bool]:
        out = await _run(
            self._exe,
            "-e",
            "set s to get volume settings",
            "-e",
            'return (output volume of s as text) & "," & (output muted of s as text)',
        )
        return parse_mac(out)

    # Scripts are built only from integers and booleans, never from phone text.
    async def set_level(self, level: int) -> None:
        await _run(self._exe, "-e", f"set volume output volume {int(level)}")

    async def set_muted(self, muted: bool) -> None:
        await _run(self._exe, "-e", f"set volume output muted {'true' if muted else 'false'}")


def parse_mac(out: str) -> tuple[int, bool]:
    level_text, _, muted_text = out.strip().partition(",")
    try:
        level = int(float(level_text))
    except ValueError as exc:
        raise VolumeError(out) from exc
    return max(0, min(100, level)), muted_text.strip() == "true"


class LinuxVolume:
    name = "pactl"
    SINK = "@DEFAULT_SINK@"

    def __init__(self, exe: str) -> None:
        self._exe = exe

    async def get(self) -> tuple[int, bool]:
        volume = await _run(self._exe, "get-sink-volume", self.SINK)
        mute = await _run(self._exe, "get-sink-mute", self.SINK)
        return parse_pactl(volume, mute)

    async def set_level(self, level: int) -> None:
        await _run(self._exe, "set-sink-volume", self.SINK, f"{int(level)}%")

    async def set_muted(self, muted: bool) -> None:
        await _run(self._exe, "set-sink-mute", self.SINK, "1" if muted else "0")


def parse_pactl(volume_out: str, mute_out: str) -> tuple[int, bool]:
    match = re.search(r"(\d+)%", volume_out)
    if match is None:
        raise VolumeError(volume_out)
    return max(0, min(100, int(match.group(1)))), "yes" in mute_out.lower()


def create_volume_backend(os_name: OsName) -> VolumeBackend | None:
    if os_name == "windows":
        return WindowsVolume()
    if os_name == "macos":
        exe = shutil.which("osascript")
        return MacVolume(exe) if exe else None
    exe = shutil.which("pactl")
    return LinuxVolume(exe) if exe else None


class VolumeService:
    def __init__(self, agent: Agent, backend: VolumeBackend | None, keys: MediaKeys) -> None:
        self._agent = agent
        self._backend = backend
        self._keys = keys
        self._state: tuple[int, bool] | None = None
        self._task: asyncio.Task[None] | None = None
        self._failing = False

    def register(self) -> None:
        router = self._agent.router
        router.register("volume.set", self._set)
        router.register("volume.step", self._step)
        router.register("volume.mute", self._mute)
        self._agent.on_connect.append(self._send_state)
        self._agent.on_startup.append(self.start)
        self._agent.on_shutdown.append(self.stop)
        if self._backend is not None:
            self._agent.set_feature("volume", True)
        elif self._keys.available:
            self._agent.set_feature(
                "volume", True, "Only volume keys are available on this laptop."
            )
        else:
            self._agent.set_feature(
                "volume", False, "Volume control isn't available on this laptop."
            )

    @property
    def state(self) -> tuple[int, bool] | None:
        return self._state

    async def start(self) -> None:
        if self._backend is None:
            return
        await self.refresh(broadcast=False)
        self._task = asyncio.get_running_loop().create_task(self._poll())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _poll(self) -> None:
        while True:
            await asyncio.sleep(POLL_SECONDS)
            await self.refresh()

    async def refresh(self, *, broadcast: bool = True) -> None:
        if self._backend is None:
            return
        try:
            state = await self._backend.get()
        except VolumeError as exc:
            if not self._failing:
                log_event(log, "volume_read_failed", level=30, error=str(exc))
            self._failing = True
            return
        self._failing = False
        if state != self._state:
            self._state = state
            if broadcast:
                await self._agent.hub.broadcast("volume.state", self._payload(state))

    @staticmethod
    def _payload(state: tuple[int, bool]) -> VolumeState:
        return VolumeState(level=state[0], muted=state[1])

    async def _send_state(self, conn: Connection) -> None:
        if self._state is not None:
            await conn.send("volume.state", self._payload(self._state))

    async def set_level(self, level: int) -> None:
        if self._backend is None:
            raise ActionError("Setting an exact volume isn't available on this laptop.")
        try:
            await self._backend.set_level(max(0, min(100, level)))
        except VolumeError as exc:
            raise ActionError("Couldn't change the volume.") from exc
        await self.refresh()

    async def _set(self, _conn: Connection, p: VolumeSet) -> None:
        await self.set_level(p.level)

    async def _step(self, _conn: Connection, p: VolumeStep) -> None:
        if self._backend is None:
            if not self._keys.volume_step(p.delta):
                raise ActionError("Volume control isn't available on this laptop.")
            return
        if self._state is None:
            await self.refresh(broadcast=False)
        current = self._state[0] if self._state is not None else 50
        await self.set_level(current + p.delta)

    async def _mute(self, _conn: Connection, p: VolumeMute) -> None:
        if self._backend is None:
            if not self._keys.toggle_mute():
                raise ActionError("Volume control isn't available on this laptop.")
            return
        try:
            await self._backend.set_muted(p.muted)
        except VolumeError as exc:
            raise ActionError("Couldn't change the volume.") from exc
        await self.refresh()

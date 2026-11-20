"""POST /api/upload: an owner phone sends a photo or file to the laptop.

The file is streamed to ``~/Downloads/LapRemote`` under a cleaned name, never overwriting and
never opened or run. On Windows it gets the "downloaded from the internet" mark (Zone.Identifier),
so SmartScreen checks it if someone opens it later.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import Toast
from lapremote.security.pairing import Device

log = get_logger("upload")

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
FREE_SPACE_MARGIN = 200 * 1024 * 1024
MAX_NAME_CHARS = 120
CHUNK = 64 * 1024
WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
SAVED_TO = f"Downloads{os.sep}LapRemote"
ZONE_INTERNET = "[ZoneTransfer]\r\nZoneId=3\r\n"


def downloads_folder() -> Path:
    return Path.home() / "Downloads" / "LapRemote"


def clean_name(raw: str) -> str:
    """A safe file name: no folders, no reserved names, no control or path characters."""
    name = unicodedata.normalize("NFC", unquote(raw or ""))
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = UNSAFE_CHARS.sub("_", name).strip().strip(".").strip()
    if not name:
        name = "file"
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    if stem.upper().split(".")[0] in WINDOWS_RESERVED:
        stem = "_" + stem
    ext = ext[:16]
    stem = stem[: MAX_NAME_CHARS - len(ext) - 1] if ext else stem[:MAX_NAME_CHARS]
    return f"{stem}.{ext}" if ext else stem


def free_path(folder: Path, name: str) -> Path:
    """``name`` in ``folder``, or ``name (2)``, ``name (3)``... so nothing is overwritten."""
    candidate = folder / name
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    number = 2
    while candidate.exists():
        suffix = f" ({number})"
        candidate = folder / (f"{stem}{suffix}.{ext}" if ext else f"{stem}{suffix}")
        number += 1
    return candidate


def mark_from_internet(path: Path) -> None:
    if sys.platform != "win32":
        return
    try:
        with Path(f"{path}:Zone.Identifier").open("w", encoding="ascii") as stream:
            stream.write(ZONE_INTERNET)
    except OSError:
        return  # not NTFS: nothing to mark


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


def register_upload(
    app: FastAPI,
    agent: Agent,
    origin_allowed: Callable[[str | None, str | None], bool],
    folder: Callable[[], Path] = downloads_folder,
) -> None:
    busy: set[str] = set()

    def authorize(request: Request) -> Device | JSONResponse:
        if not origin_allowed(request.headers.get("origin"), request.headers.get("host")):
            return _error(403, "Not allowed from this page.")
        device_id = request.headers.get("x-lapremote-device", "")
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        device = agent.devices.verify(device_id, token) if device_id and token else None
        if device is None:
            return _error(401, "Pair this phone first.")
        if device.role != "owner":
            return _error(403, "Only the owner can send files to this laptop.")
        return device

    @app.post("/api/upload", include_in_schema=False)
    async def upload(request: Request) -> JSONResponse:
        device = authorize(request)
        if isinstance(device, JSONResponse):
            return device
        try:
            size = int(request.headers.get("content-length", ""))
        except ValueError:
            return _error(400, "The file size is missing.")
        if size <= 0:
            return _error(400, "That file is empty.")
        if size > MAX_UPLOAD_BYTES:
            return _error(413, "Files can be up to 100 MB.")
        if device.device_id in busy:
            return _error(429, "Wait for the other file to finish.")

        target_dir = folder()
        target_dir.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(target_dir).free < size + FREE_SPACE_MARGIN:
            return _error(400, "There isn't enough space on the laptop.")
        name = clean_name(request.headers.get("x-lapremote-filename", ""))
        busy.add(device.device_id)
        partial = target_dir / f".{name}.{os.getpid()}.part"
        try:
            received = 0
            with partial.open("wb") as out:
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > size or received > MAX_UPLOAD_BYTES:
                        partial.unlink(missing_ok=True)
                        return _error(413, "Files can be up to 100 MB.")
                    out.write(chunk)
            if received != size:
                partial.unlink(missing_ok=True)
                return _error(400, "The file didn't arrive completely. Try again.")
            final = free_path(target_dir, name)
            partial.replace(final)
            mark_from_internet(final)
        except OSError:
            partial.unlink(missing_ok=True)
            return _error(400, "Couldn't save the file on the laptop.")
        finally:
            busy.discard(device.device_id)

        # Only the size and the device: the file name can be private.
        log_event(log, "file_received", device=device.device_id, bytes=received)
        for conn in agent.hub.for_device(device.device_id):
            await conn.send(
                "toast",
                Toast(
                    level="success", message=f"Saved {final.name} to Downloads\\LapRemote."[:300]
                ),
            )
        return JSONResponse({"ok": True, "name": final.name, "size": received})

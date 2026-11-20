"""Per-app button layouts, stored in ~/.lapremote/layouts.json and shared by every phone.

A layout's buttons only name existing, allowlisted actions (a key combo, a media command, a
seek, a volume step or a shortcut), and the phone runs them by sending the usual messages, so a
layout can't do anything the phone's own buttons couldn't.

The defaults include call controls for Zoom, Microsoft Teams and Google Meet, using each app's
own keyboard shortcuts for this laptop's OS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import Layout, LayoutsDelete, LayoutsSave, LayoutsState, OsName
from lapremote.router import ActionError
from lapremote.storage import write_json_atomic

log = get_logger("layouts")

MAX_LAYOUTS = 40
_LIST = TypeAdapter(list[Layout])


Combo = tuple[str, ...]  # key name, then modifiers

# Each app's own shortcuts. macOS uses Cmd (meta) and Option (alt) where the apps do.
CALL_KEYS: dict[str, dict[str, Combo]] = {
    "windows": {
        "zoom_mute": ("a", "alt"),
        "zoom_camera": ("v", "alt"),
        "zoom_share": ("s", "alt"),
        "zoom_hand": ("y", "alt"),
        "zoom_chat": ("h", "alt"),
        "zoom_leave": ("q", "alt"),
        "meet_hand": ("h", "ctrl", "alt"),
        "meet_chat": ("c", "ctrl", "alt"),
        "vlc_back": ("left", "alt"),
        "vlc_forward": ("right", "alt"),
    },
    "macos": {
        "zoom_mute": ("a", "meta", "shift"),
        "zoom_camera": ("v", "meta", "shift"),
        "zoom_share": ("s", "meta", "shift"),
        "zoom_hand": ("y", "alt"),
        "zoom_chat": ("h", "meta", "shift"),
        "zoom_leave": ("w", "meta"),
        "meet_hand": ("h", "ctrl", "meta"),
        "meet_chat": ("c", "ctrl", "meta"),
        "vlc_back": ("left", "meta", "alt"),
        "vlc_forward": ("right", "meta", "alt"),
    },
}


def _key(label: str, combo: Combo, icon: str) -> dict[str, Any]:
    key, *mods = combo
    action = {"type": "key", "key": key, "modifiers": mods}
    return {"label": label, "icon": icon, "action": action}


def _media(label: str, command: str, icon: str) -> dict[str, Any]:
    return {"label": label, "icon": icon, "action": {"type": "media", "command": command}}


def default_layouts(os_name: OsName) -> list[Layout]:
    k = CALL_KEYS["macos" if os_name == "macos" else "windows"]
    cmd = "meta" if os_name == "macos" else "ctrl"
    raw: list[dict[str, Any]] = [
        {
            "id": "zoom",
            "name": "Zoom call",
            "match": {"processes": ["zoom.exe", "zoom.us", "zoom"], "titles": ["Zoom Meeting"]},
            "buttons": [
                _key("Mute", k["zoom_mute"], "mic"),
                _key("Camera", k["zoom_camera"], "video"),
                _key("Share screen", k["zoom_share"], "screen-share"),
                _key("Raise hand", k["zoom_hand"], "hand"),
                _key("Chat", k["zoom_chat"], "message"),
                _key("Leave", k["zoom_leave"], "phone-off"),
            ],
        },
        {
            "id": "teams",
            "name": "Teams call",
            "match": {
                "processes": ["ms-teams.exe", "teams.exe", "microsoft teams"],
                "titles": ["Microsoft Teams"],
            },
            "buttons": [
                _key("Mute", ("m", cmd, "shift"), "mic"),
                _key("Camera", ("o", cmd, "shift"), "video"),
                _key("Share screen", ("e", cmd, "shift"), "screen-share"),
                _key("Raise hand", ("k", cmd, "shift"), "hand"),
                _key("Leave", ("h", cmd, "shift"), "phone-off"),
            ],
        },
        {
            "id": "meet",
            "name": "Google Meet",
            "match": {"titles": ["Meet - ", "Google Meet"]},
            "buttons": [
                _key("Mute", ("d", cmd), "mic"),
                _key("Camera", ("e", cmd), "video"),
                _key("Raise hand", k["meet_hand"], "hand"),
                _key("Chat", k["meet_chat"], "message"),
                _key("Leave (closes tab)", ("w", cmd), "phone-off"),
            ],
        },
        {
            "id": "vlc",
            "name": "VLC",
            "match": {"processes": ["vlc.exe", "vlc"]},
            "buttons": [
                _key("Play / pause", ("space",), "play"),
                _key("Back 10s", k["vlc_back"], "rewind"),
                _key("Forward 10s", k["vlc_forward"], "fast-forward"),
                _key("Fullscreen", ("f",), "maximize"),
                _key("Subtitles", ("v",), "captions"),
                _key("Mute", ("m",), "volume-x"),
                _key("Volume up", ("up", cmd), "volume-2"),
                _key("Volume down", ("down", cmd), "volume-1"),
            ],
        },
        {
            "id": "spotify",
            "name": "Spotify",
            "match": {"processes": ["spotify.exe", "spotify"], "sites": ["spotify_web"]},
            "buttons": [
                _media("Play / pause", "toggle", "play"),
                _media("Previous", "prev", "skip-back"),
                _media("Next", "next", "skip-forward"),
                _key("Shuffle", ("s", cmd), "shuffle"),
                _key("Repeat", ("r", cmd), "repeat"),
                _key("Volume up", ("up", cmd), "volume-2"),
                _key("Volume down", ("down", cmd), "volume-1"),
            ],
        },
        {
            "id": "youtube",
            "name": "YouTube",
            "match": {"sites": ["youtube"]},
            "buttons": [
                _key("Play / pause", ("k",), "play"),
                _key("Back 10s", ("j",), "rewind"),
                _key("Forward 10s", ("l",), "fast-forward"),
                _key("Fullscreen", ("f",), "maximize"),
                _key("Captions", ("c",), "captions"),
                _key("Mute", ("m",), "volume-x"),
                _key("Next video", ("n", "shift"), "skip-forward"),
                _key("Theater", ("t",), "rectangle-horizontal"),
            ],
        },
    ]
    return _LIST.validate_python(raw)


class LayoutStore:
    def __init__(self, path: Path, os_name: OsName) -> None:
        self._path = path
        self._os = os_name
        self._items = self._load()

    def _load(self) -> list[Layout]:
        if self._path.exists():
            try:
                return _LIST.validate_json(self._path.read_bytes())
            except (OSError, ValidationError):
                self._path.replace(self._path.with_suffix(".json.broken"))
                log_event(log, "layouts_file_broken", level=30)
        items = default_layouts(self._os)
        self._items = items
        self._save()
        return items

    def items(self) -> list[Layout]:
        return list(self._items)

    def get(self, layout_id: str) -> Layout | None:
        return next((item for item in self._items if item.id == layout_id), None)

    def _save(self) -> None:
        write_json_atomic(
            self._path, [item.model_dump(mode="json", by_alias=True) for item in self._items]
        )

    def upsert(self, layout: Layout) -> None:
        for i, existing in enumerate(self._items):
            if existing.id == layout.id:
                self._items[i] = layout
                self._save()
                return
        if len(self._items) >= MAX_LAYOUTS:
            msg = "too many layouts"
            raise OverflowError(msg)
        self._items.append(layout)
        self._save()

    def delete(self, layout_id: str) -> bool:
        before = len(self._items)
        self._items = [item for item in self._items if item.id != layout_id]
        if len(self._items) != before:
            self._save()
            return True
        return False


class LayoutService:
    def __init__(self, agent: Agent, store: LayoutStore) -> None:
        self._agent = agent
        self._store = store

    @property
    def store(self) -> LayoutStore:
        return self._store

    def register(self) -> None:
        self._agent.router.register("layouts.save", self._save)
        self._agent.router.register("layouts.delete", self._delete)
        self._agent.on_connect.append(self._send_state)

    def state(self) -> LayoutsState:
        return LayoutsState(layouts=self._store.items())

    async def _send_state(self, conn: Connection) -> None:
        await conn.send("layouts.state", self.state())

    async def _broadcast(self) -> None:
        await self._agent.hub.broadcast("layouts.state", self.state())

    async def _save(self, _conn: Connection, p: LayoutsSave) -> None:
        # Normalise matching so the phone's case-insensitive compare is simple.
        layout = p.layout
        match = layout.match.model_copy(
            update={
                "processes": [x.strip().lower() for x in layout.match.processes if x.strip()],
                "titles": [x.strip() for x in layout.match.titles if x.strip()],
            }
        )
        try:
            self._store.upsert(layout.model_copy(update={"match": match}))
        except OverflowError as exc:
            raise ActionError(f"You can have up to {MAX_LAYOUTS} layouts.") from exc
        await self._broadcast()

    async def _delete(self, _conn: Connection, p: LayoutsDelete) -> None:
        if not self._store.delete(p.layout_id):
            raise ActionError("That layout doesn't exist anymore.")
        await self._broadcast()

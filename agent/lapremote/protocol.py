"""LapRemote wire protocol - the single source of truth.

Every message is a JSON envelope ``{v, id, type, payload}``. This module holds
the pydantic model of every payload, the role and reply rules for each client
message, and a normalised schema export that the web client's zod mirror is
checked against (see ``shared/protocol.schema.json`` and docs/PROTOCOL.md).
"""

from __future__ import annotations

import json
import string
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    WithJsonSchema,
    model_validator,
)
from pydantic.alias_generators import to_camel

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 256 * 1024

# --------------------------------------------------------------------------
# Shared building blocks
# --------------------------------------------------------------------------


class WireModel(BaseModel):
    """camelCase on the wire, snake_case in Python, unknown fields rejected."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        ser_json_inf_nan="null",
    )


Role = Literal["owner", "guest"]
OsName = Literal["windows", "macos", "linux"]
Button = Literal["left", "right", "middle"]
Modifier = Literal["ctrl", "alt", "shift", "meta"]
PowerActionName = Literal["lock", "sleep", "shutdown", "restart"]
TimerMode = Literal["minutes", "end_of_media"]
TimerThen = Literal["pause", "pause_lock", "pause_sleep"]
MediaStatus = Literal["playing", "paused", "stopped"]
ContextCategory = Literal["browser", "music", "video", "presentation", "desktop", "other"]
Site = Literal["youtube", "netflix", "prime", "spotify_web", "generic"]
ToastLevel = Literal["info", "success", "warn", "error"]
AuthFailReason = Literal["invalid_code", "expired_code", "bad_token", "rate_limited"]

IdStr = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]
Coord = Annotated[float, Field(ge=-10_000, le=10_000, allow_inf_nan=False)]
Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Level = Annotated[int, Field(ge=0, le=100)]
MonitorIndex = Annotated[int, Field(ge=0, le=16)]
Timestamp = Annotated[float, Field(ge=0, allow_inf_nan=False)]

# Key names accepted by key.press. Anything else is rejected before it can
# reach the keyboard backend.
KEY_NAMES: tuple[str, ...] = (
    *string.ascii_lowercase,
    *string.digits,
    *(f"f{n}" for n in range(1, 25)),
    "enter",
    "esc",
    "tab",
    "backspace",
    "delete",
    "insert",
    "space",
    "up",
    "down",
    "left",
    "right",
    "home",
    "end",
    "pageup",
    "pagedown",
    "capslock",
    "printscreen",
    "menu",
    "`",
    "-",
    "=",
    "[",
    "]",
    "\\",
    ";",
    "'",
    ",",
    ".",
    "/",
    "media_play_pause",
    "media_next",
    "media_prev",
    "volume_up",
    "volume_down",
    "volume_mute",
)
_KEY_SET = frozenset(KEY_NAMES)


def _check_key(value: str) -> str:
    if value not in _KEY_SET:
        msg = f"unknown key {value!r}"
        raise ValueError(msg)
    return value


KeyName = Annotated[
    str,
    AfterValidator(_check_key),
    WithJsonSchema({"type": "string", "enum": list(KEY_NAMES)}),
]


class Empty(WireModel):
    """Payload for messages that carry no data."""


# --------------------------------------------------------------------------
# Shared data models
# --------------------------------------------------------------------------


class Shortcut(WireModel):
    id: IdStr
    name: str = Field(min_length=1, max_length=40)
    kind: Literal["url", "app"]
    url: str | None = Field(default=None, max_length=2048)
    app: str | None = Field(default=None, max_length=1024)
    icon: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _target_matches_kind(self) -> Self:
        if self.kind == "url":
            if self.url is None or not self.url.startswith(("http://", "https://")):
                msg = "url shortcuts need an http or https url"
                raise ValueError(msg)
            if self.app is not None:
                msg = "url shortcuts cannot have an app"
                raise ValueError(msg)
        else:
            if not self.app:
                msg = "app shortcuts need an app"
                raise ValueError(msg)
            if self.url is not None:
                msg = "app shortcuts cannot have a url"
                raise ValueError(msg)
        return self


class VolumeSetStep(WireModel):
    type: Literal["volume.set"]
    level: Level


class BrightnessSetStep(WireModel):
    type: Literal["brightness.set"]
    level: Level


class LaunchOpenStep(WireModel):
    type: Literal["launch.open"]
    shortcut_id: IdStr


class MediaPlayStep(WireModel):
    type: Literal["media.play"]


class MediaPauseStep(WireModel):
    type: Literal["media.pause"]


class WaitStep(WireModel):
    type: Literal["wait"]
    ms: int = Field(ge=0, le=600_000)


SceneStep = Annotated[
    VolumeSetStep | BrightnessSetStep | LaunchOpenStep | MediaPlayStep | MediaPauseStep | WaitStep,
    Field(discriminator="type"),
]


class Scene(WireModel):
    id: IdStr
    name: str = Field(min_length=1, max_length=40)
    steps: list[SceneStep] = Field(min_length=1, max_length=50)


class FeatureStatus(WireModel):
    available: bool
    reason: str | None = None


class Features(WireModel):
    input: FeatureStatus
    media: FeatureStatus
    volume: FeatureStatus
    brightness: FeatureStatus
    preview: FeatureStatus
    context: FeatureStatus
    power: FeatureStatus
    launcher: FeatureStatus
    scenes: FeatureStatus
    timer: FeatureStatus
    ai: FeatureStatus
    secure_context: bool


class MediaSession(WireModel):
    id: str
    app_id: str
    app_name: str
    title: str
    artist: str
    album: str
    artwork_id: str | None
    artwork: str | None
    status: MediaStatus
    position: float | None
    duration: float | None
    rate: float
    can_seek: bool
    can_next: bool
    can_prev: bool
    updated_at: Timestamp


class MonitorInfo(WireModel):
    index: MonitorIndex
    left: int
    top: int
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    primary: bool


class DeviceInfo(WireModel):
    device_id: str
    name: str
    platform: str
    role: Role
    paired_at: Timestamp
    last_seen_at: Timestamp | None
    online: bool


AI_ACTION_TYPES: tuple[str, ...] = (
    "media.toggle",
    "media.play",
    "media.pause",
    "media.next",
    "media.prev",
    "media.seek",
    "media.select",
    "volume.set",
    "volume.step",
    "volume.mute",
    "brightness.set",
    "power.action",
    "launch.open",
    "scene.run",
    "timer.set",
    "timer.cancel",
    "key.press",
    "key.text",
    "wait",
)
AiActionType = Annotated[
    str,
    AfterValidator(lambda v: v if v in AI_ACTION_TYPES else _bad_action(v)),
    WithJsonSchema({"type": "string", "enum": list(AI_ACTION_TYPES)}),
]


def _bad_action(value: str) -> str:
    msg = f"action {value!r} is not allowed"
    raise ValueError(msg)


class AiAction(WireModel):
    type: AiActionType
    payload: dict[str, Any] = Field(default_factory=dict)


class AiStepResult(WireModel):
    type: str
    ok: bool
    error: str | None = None


# --------------------------------------------------------------------------
# Client -> Agent payloads
# --------------------------------------------------------------------------


class AuthPair(WireModel):
    code: str = Field(pattern=r"^\d{6}$")
    device_name: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=32)


class AuthResume(WireModel):
    device_id: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=1, max_length=128)


class InputMove(WireModel):
    dx: Coord
    dy: Coord


class InputButton(WireModel):
    button: Button


class InputScroll(WireModel):
    dx: Coord
    dy: Coord


class InputZoom(WireModel):
    dir: Literal["in", "out"]


class InputAbsClick(WireModel):
    x: Unit
    y: Unit
    monitor: MonitorIndex
    button: Button


class KeyPress(WireModel):
    key: KeyName
    modifiers: list[Modifier] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _unique_modifiers(self) -> Self:
        if len(set(self.modifiers)) != len(self.modifiers):
            msg = "modifiers must be unique"
            raise ValueError(msg)
        return self


class KeyText(WireModel):
    text: str = Field(min_length=1, max_length=2000)


class MediaTarget(WireModel):
    session_id: str | None = None


class MediaSeek(WireModel):
    session_id: str | None = None
    to: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    by: float | None = Field(default=None, ge=-86_400, le=86_400, allow_inf_nan=False)

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.to is None) == (self.by is None):
            msg = "send exactly one of 'to' or 'by'"
            raise ValueError(msg)
        return self


class MediaSelect(WireModel):
    session_id: str = Field(min_length=1)


class MediaArtworkRequest(WireModel):
    artwork_id: str = Field(min_length=1, max_length=64)


class VolumeSet(WireModel):
    level: Level


class VolumeStep(WireModel):
    delta: int = Field(ge=-100, le=100)


class VolumeMute(WireModel):
    muted: bool


class BrightnessSet(WireModel):
    level: Level


class PowerPrepare(WireModel):
    action: PowerActionName


class PowerAction(WireModel):
    action: PowerActionName
    confirm_token: str = Field(min_length=1, max_length=128)


class LaunchOpen(WireModel):
    shortcut_id: IdStr


class SceneRun(WireModel):
    scene_id: IdStr


class TimerSet(WireModel):
    minutes: float | None = Field(default=None, gt=0, le=1440, allow_inf_nan=False)
    mode: TimerMode
    then: TimerThen

    @model_validator(mode="after")
    def _minutes_for_minutes_mode(self) -> Self:
        if self.mode == "minutes" and self.minutes is None:
            msg = "minutes is required when mode is 'minutes'"
            raise ValueError(msg)
        return self


class PreviewStart(WireModel):
    fps: int = Field(default=8, ge=1, le=15)
    width: int = Field(default=480, ge=160, le=1920)
    monitor: MonitorIndex = 0


class PreviewAck(WireModel):
    frame: int = Field(ge=0)


class AiCommand(WireModel):
    text: str = Field(min_length=1, max_length=500)


class AiConfirm(WireModel):
    plan_id: str = Field(min_length=1, max_length=64)
    approve: bool


class DevicesRevoke(WireModel):
    device_id: str = Field(min_length=1, max_length=64)


class DevicesRole(WireModel):
    device_id: str = Field(min_length=1, max_length=64)
    role: Role


class ShortcutsSave(WireModel):
    shortcut: Shortcut


class ShortcutsDelete(WireModel):
    shortcut_id: IdStr


class ShortcutsReorder(WireModel):
    ids: list[IdStr] = Field(max_length=200)


class ScenesSave(WireModel):
    scene: Scene


class ScenesDelete(WireModel):
    scene_id: IdStr


class Ping(WireModel):
    t: float = Field(allow_inf_nan=False)


# --------------------------------------------------------------------------
# Agent -> Client payloads
# --------------------------------------------------------------------------


class Ack(WireModel):
    id: str
    ok: bool
    error: str | None = None


class AuthOk(WireModel):
    device_id: str
    token: str | None = None
    role: Role
    host_name: str
    os: OsName
    features: Features


class AuthFail(WireModel):
    reason: AuthFailReason


class MediaState(WireModel):
    sessions: list[MediaSession]
    current_id: str | None
    ts: Timestamp


class MediaArtwork(WireModel):
    artwork_id: str
    artwork: str | None


class ContextState(WireModel):
    app: str
    process_name: str
    window_title: str
    category: ContextCategory
    site: Site | None
    ts: Timestamp


class VolumeState(WireModel):
    level: Level
    muted: bool


class BrightnessState(WireModel):
    level: Level | None
    supported: bool


class TimerState(WireModel):
    active: bool
    ends_at: Timestamp | None
    mode: TimerMode | None
    then: TimerThen | None


class PreviewMeta(WireModel):
    width: int
    height: int
    monitors: list[MonitorInfo]


class AiPlan(WireModel):
    plan_id: str
    reply: str
    actions: list[AiAction]
    needs_confirm: bool


class AiResult(WireModel):
    plan_id: str
    steps: list[AiStepResult]


class Toast(WireModel):
    level: ToastLevel
    message: str = Field(max_length=300)


class Pong(WireModel):
    t: float


class DevicesState(WireModel):
    devices: list[DeviceInfo]


class PowerToken(WireModel):
    action: PowerActionName
    confirm_token: str
    expires_at: Timestamp


class ShortcutsState(WireModel):
    shortcuts: list[Shortcut]


class ScenesState(WireModel):
    scenes: list[Scene]


# --------------------------------------------------------------------------
# Envelope and registries
# --------------------------------------------------------------------------


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: Literal[1]
    id: str = Field(min_length=1, max_length=64)
    type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


RequiredRole = Literal["none", "authed", "guest", "owner"]
# How the agent answers a client message:
#   ack    - an ``ack`` with ok true/false
#   reply  - a dedicated reply message on success (an ``ack`` with ok false on error)
#   none   - fire-and-forget, nothing is sent back
ReplyKind = Literal["ack", "reply", "none"]


@dataclass(frozen=True)
class ClientMessage:
    payload: type[WireModel]
    role: RequiredRole
    reply: ReplyKind


CLIENT_MESSAGES: dict[str, ClientMessage] = {
    "auth.pair": ClientMessage(AuthPair, "none", "reply"),
    "auth.resume": ClientMessage(AuthResume, "none", "reply"),
    "input.move": ClientMessage(InputMove, "guest", "none"),
    "input.click": ClientMessage(InputButton, "owner", "ack"),
    "input.down": ClientMessage(InputButton, "owner", "ack"),
    "input.up": ClientMessage(InputButton, "owner", "ack"),
    "input.scroll": ClientMessage(InputScroll, "owner", "none"),
    "input.zoom": ClientMessage(InputZoom, "owner", "ack"),
    "input.absclick": ClientMessage(InputAbsClick, "owner", "ack"),
    "key.press": ClientMessage(KeyPress, "owner", "ack"),
    "key.text": ClientMessage(KeyText, "owner", "ack"),
    "media.toggle": ClientMessage(MediaTarget, "guest", "ack"),
    "media.play": ClientMessage(MediaTarget, "guest", "ack"),
    "media.pause": ClientMessage(MediaTarget, "guest", "ack"),
    "media.next": ClientMessage(MediaTarget, "guest", "ack"),
    "media.prev": ClientMessage(MediaTarget, "guest", "ack"),
    "media.seek": ClientMessage(MediaSeek, "guest", "ack"),
    "media.select": ClientMessage(MediaSelect, "guest", "ack"),
    "media.artwork": ClientMessage(MediaArtworkRequest, "guest", "reply"),
    "volume.set": ClientMessage(VolumeSet, "guest", "ack"),
    "volume.step": ClientMessage(VolumeStep, "guest", "ack"),
    "volume.mute": ClientMessage(VolumeMute, "guest", "ack"),
    "brightness.set": ClientMessage(BrightnessSet, "owner", "ack"),
    "power.prepare": ClientMessage(PowerPrepare, "owner", "reply"),
    "power.action": ClientMessage(PowerAction, "owner", "ack"),
    "launch.open": ClientMessage(LaunchOpen, "owner", "ack"),
    "scene.run": ClientMessage(SceneRun, "owner", "ack"),
    "timer.set": ClientMessage(TimerSet, "owner", "ack"),
    "timer.cancel": ClientMessage(Empty, "owner", "ack"),
    "preview.start": ClientMessage(PreviewStart, "owner", "ack"),
    "preview.stop": ClientMessage(Empty, "owner", "ack"),
    "preview.ack": ClientMessage(PreviewAck, "owner", "none"),
    "ai.command": ClientMessage(AiCommand, "owner", "reply"),
    "ai.confirm": ClientMessage(AiConfirm, "owner", "ack"),
    "devices.list": ClientMessage(Empty, "owner", "reply"),
    "devices.revoke": ClientMessage(DevicesRevoke, "owner", "ack"),
    "devices.role": ClientMessage(DevicesRole, "owner", "ack"),
    "shortcuts.save": ClientMessage(ShortcutsSave, "owner", "ack"),
    "shortcuts.delete": ClientMessage(ShortcutsDelete, "owner", "ack"),
    "shortcuts.reorder": ClientMessage(ShortcutsReorder, "owner", "ack"),
    "scenes.save": ClientMessage(ScenesSave, "owner", "ack"),
    "scenes.delete": ClientMessage(ScenesDelete, "owner", "ack"),
    "ping": ClientMessage(Ping, "authed", "reply"),
}

AGENT_MESSAGES: dict[str, type[WireModel]] = {
    "ack": Ack,
    "auth.ok": AuthOk,
    "auth.fail": AuthFail,
    "media.state": MediaState,
    "media.artwork": MediaArtwork,
    "context.state": ContextState,
    "volume.state": VolumeState,
    "brightness.state": BrightnessState,
    "timer.state": TimerState,
    "preview.meta": PreviewMeta,
    "ai.plan": AiPlan,
    "ai.result": AiResult,
    "toast": Toast,
    "pong": Pong,
    "devices.state": DevicesState,
    "power.token": PowerToken,
    "shortcuts.state": ShortcutsState,
    "scenes.state": ScenesState,
}

# Binary preview frames: 8-byte big-endian header (uint32 frame, uint32 monitor) + JPEG.
PREVIEW_HEADER_FORMAT = ">II"
PREVIEW_HEADER_BYTES = 8


def encode(type_: str, payload: WireModel, message_id: str) -> str:
    """Serialise an agent message envelope to JSON text."""
    if type_ not in AGENT_MESSAGES:
        msg = f"unknown agent message type {type_!r}"
        raise KeyError(msg)
    body = payload.model_dump(mode="json", by_alias=True)
    return json.dumps(
        {"v": PROTOCOL_VERSION, "id": message_id, "type": type_, "payload": body},
        separators=(",", ":"),
        allow_nan=False,
    )


# --------------------------------------------------------------------------
# Normalised schema export (compared against the zod mirror)
# --------------------------------------------------------------------------

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "shared" / "protocol.schema.json"


def _resolve(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        node = defs[node["$ref"].split("/")[-1]]
    return node


def _normalise(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    node = _resolve(node, defs)
    variants = node.get("anyOf") or node.get("oneOf")
    if variants is not None:
        members = [_normalise(v, defs) for v in variants]
        nullable = {"type": "null"} in members
        rest = [m for m in members if m != {"type": "null"}]
        if len(rest) == 1:
            base: dict[str, Any] = rest[0]
        else:
            base = {"union": sorted(rest, key=lambda m: json.dumps(m, sort_keys=True))}
        return {"nullable": base} if nullable else base
    if "const" in node:
        return {"enum": [node["const"]]}
    if "enum" in node:
        return {"enum": sorted(node["enum"])}
    kind = node.get("type")
    if kind == "object":
        props = node.get("properties")
        if props is None:
            return {"type": "record"}
        required = set(node.get("required", []))
        return {
            "object": {
                name: {"required": name in required, "schema": _normalise(sub, defs)}
                for name, sub in sorted(props.items())
            }
        }
    if kind == "array":
        return {"array": _normalise(node.get("items", {}), defs)}
    if kind in ("string", "integer", "number", "boolean", "null"):
        return {"type": kind}
    return {"type": "unknown"}


def _model_descriptor(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(by_alias=True, mode="validation")
    return _normalise(schema, schema.get("$defs", {}))


def schema_descriptor() -> dict[str, Any]:
    """Normalised structure of every message payload, by direction and type."""
    return {
        "version": PROTOCOL_VERSION,
        "clientToAgent": {
            name: {
                "role": spec.role,
                "reply": spec.reply,
                "payload": _model_descriptor(spec.payload),
            }
            for name, spec in sorted(CLIENT_MESSAGES.items())
        },
        "agentToClient": {
            name: {"payload": _model_descriptor(model)}
            for name, model in sorted(AGENT_MESSAGES.items())
        },
    }


def render_schema() -> str:
    return json.dumps(schema_descriptor(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    """``python -m lapremote.protocol --write`` regenerates shared/protocol.schema.json."""
    if argv == ["--write"]:
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_text(render_schema(), encoding="utf-8", newline="\n")
        print(f"wrote {SCHEMA_PATH}")
        return 0
    if argv == ["--check"]:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current != render_schema():
            print("shared/protocol.schema.json is stale - run with --write")
            return 1
        return 0
    print("usage: python -m lapremote.protocol --write | --check")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

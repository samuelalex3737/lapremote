"""Turns a sentence into a short list of allowlisted actions.

The model only ever proposes data. Its answer must be one JSON object
``{"reply": str, "actions": [{"type", "payload"}]}``. Every action type is checked against
``AI_ACTION_TYPES`` and every payload against the protocol model for that type, so the
planner can never ask for anything the phone itself couldn't. Anything else is dropped and
reported in the reply.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from lapremote.ai.providers import ChatMessage, ChatProvider, ProviderError
from lapremote.protocol import AI_ACTION_TYPES, AI_PAYLOADS, KEY_NAMES, AiAction
from lapremote.router import ActionError

MAX_ACTIONS = 12
LONG_TEXT = 200
MAX_REPLY = 300

NOT_UNDERSTOOD = "I couldn't turn that into something I can do. Try saying it another way."

# One line per action type, in the order the model sees them.
ACTION_NOTES: dict[str, str] = {
    "media.toggle": "Play or pause. sessionId is optional (the current player when left out).",
    "media.play": "Resume playback.",
    "media.pause": "Pause. Without sessionId it pauses every player that is playing.",
    "media.next": "Next track or next episode.",
    "media.prev": "Previous track.",
    "media.seek": "Seek. Exactly one of to (seconds from the start) or by (seconds, negative "
    "goes back). 'go back 2 minutes' is by -120.",
    "media.select": "Make another player the current one (sessionId from the context).",
    "volume.set": "Set the laptop volume, level 0-100.",
    "volume.step": "Change the volume by delta (-100 to 100).",
    "volume.mute": "Mute (muted true) or unmute (muted false).",
    "brightness.set": "Set screen brightness, level 0-100.",
    "power.action": "lock, sleep, shutdown or restart the laptop now. Always asks the person to "
    "confirm first. For 'later' or 'in N minutes' use timer.set instead.",
    "launch.open": "Open a shortcut by its id from the shortcuts list. Nothing else can be "
    "opened. To search YouTube after opening it, the steps are always: wait 4000, key.press '/', "
    "key.text with the words, key.press enter.",
    "scene.run": "Run a scene by its id from the scenes list.",
    "timer.set": "Sleep timer. mode 'minutes' with minutes, or mode 'end_of_media'. then: "
    "'pause' only pauses, 'pause_lock' pauses and locks, 'pause_sleep' pauses and puts the laptop "
    "to sleep. If the request says sleep, then is pause_sleep. If it says lock, pause_lock.",
    "timer.cancel": "Cancel the sleep timer.",
    "key.press": "Press one key with optional modifiers (ctrl, shift, alt, meta).",
    "key.text": "Type text where the cursor is.",
    "wait": "Pause between steps, ms 0-60000. Use about 4000 after opening a website.",
}


@dataclass
class PlannerContext:
    """What the laptop looks like right now, summarised for the model."""

    media: list[dict[str, Any]] = field(default_factory=list)
    current_media_id: str | None = None
    foreground: dict[str, Any] | None = None
    volume: dict[str, Any] | None = None
    brightness: int | None = None
    timer: dict[str, Any] | None = None
    shortcuts: list[dict[str, str]] = field(default_factory=list)
    scenes: list[dict[str, str]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "players": self.media,
            "currentPlayerId": self.current_media_id,
            "foregroundApp": self.foreground,
            "volume": self.volume,
            "brightness": self.brightness,
            "sleepTimer": self.timer,
            "shortcuts": self.shortcuts,
            "scenes": self.scenes,
        }


@dataclass
class PlanDraft:
    reply: str
    actions: list[AiAction]
    dropped: list[str]
    needs_confirm: bool


class MalformedPlanError(Exception):
    """The model's answer wasn't the JSON object we asked for."""


def _field_type(prop: dict[str, Any]) -> str:
    if "enum" in prop:
        return "|".join(str(v) for v in prop["enum"])
    if "anyOf" in prop:
        return next(_field_type(p) for p in prop["anyOf"] if p.get("type") != "null")
    kind = str(prop.get("type", "any"))
    if kind == "array":
        return f"[{_field_type(prop.get('items', {}))}]"
    low, high = prop.get("minimum"), prop.get("maximum")
    if low is not None and high is not None:
        return f"{kind} {low:g} to {high:g}"
    return kind


def action_signature(action_type: str) -> str:
    """``volume.set {level: integer 0 to 100}``, generated from the protocol model."""
    schema = AI_PAYLOADS[action_type].model_json_schema(by_alias=True)
    required = set(schema.get("required", []))
    fields = []
    for name, prop in schema.get("properties", {}).items():
        kind = "key name" if name == "key" else _field_type(prop)
        fields.append(f"{name}{'' if name in required else '?'}: {kind}")
    return f"{action_type} {{{', '.join(fields)}}}"


def _key_list() -> str:
    named = [k for k in KEY_NAMES if len(k) > 1 and not re.fullmatch(r"f\d+", k)]
    return (
        "a-z, 0-9, f1-f24, "
        + ", ".join(named)
        + ", and the symbols "
        + " ".join(k for k in KEY_NAMES if len(k) == 1 and not k.isalnum())
    )


EXAMPLE = (
    'Request: "open youtube and search cats"\n'
    '{"reply": "Searching YouTube for cats.", "actions": ['
    '{"type": "launch.open", "payload": {"shortcutId": "youtube"}}, '
    '{"type": "wait", "payload": {"ms": 4000}}, '
    '{"type": "key.press", "payload": {"key": "/"}}, '
    '{"type": "key.text", "payload": {"text": "cats"}}, '
    '{"type": "key.press", "payload": {"key": "enter"}}]}'
)


def build_system_prompt(context: PlannerContext) -> str:
    actions = [f"- {action_signature(t)}: {ACTION_NOTES[t]}" for t in AI_ACTION_TYPES]
    return "\n".join(
        [
            "You control a laptop for the person holding their phone. Turn their request into "
            "a short list of actions from the allowed list. You cannot run commands, open "
            "arbitrary programs or visit websites that aren't shortcuts.",
            "",
            "Answer with ONE JSON object and nothing else:",
            '{"reply": "<one short friendly sentence>", "actions": [{"type": "<action>", '
            '"payload": {...}}]}',
            "",
            "Rules:",
            "- Use only these action types and payload fields (? means optional).",
            "- Use ids exactly as they appear in the context (shortcuts, scenes, players).",
            "- If the request can't be done with these actions, return no actions and say so "
            "in reply.",
            "- Keep reply under 20 words and don't mention JSON or actions.",
            "",
            "Allowed actions:",
            *actions,
            "",
            "Key names: " + _key_list(),
            "",
            "Example:",
            EXAMPLE,
            "",
            "Laptop right now:",
            json.dumps(context.summary(), separators=(",", ":")),
        ]
    )


def _loads(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        # Some models wrap JSON in a code fence even when asked not to.
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MalformedPlanError(str(exc)) from exc
    if not isinstance(data, dict):
        raise MalformedPlanError("not an object")
    if not isinstance(data.get("actions", []), list):
        raise MalformedPlanError("actions is not a list")
    return data


def _check_ids(action: AiAction, context: PlannerContext) -> str | None:
    payload = action.payload
    shortcut_ids = {s["id"] for s in context.shortcuts}
    if action.type == "launch.open" and payload["shortcutId"] not in shortcut_ids:
        return f"there is no shortcut {payload['shortcutId']!r}"
    if action.type == "scene.run" and payload["sceneId"] not in {s["id"] for s in context.scenes}:
        return f"there is no scene {payload['sceneId']!r}"
    session_id = payload.get("sessionId")
    if session_id is not None and session_id not in {m["id"] for m in context.media}:
        return "that player isn't open"
    return None


@dataclass
class Checked:
    kept: list[AiAction]
    dropped: list[str]
    """Short descriptions of what was left out, for the reply and the log."""
    problems: list[str]
    """Exact reasons, fed back to the model when it gets a second try."""


def _describe_errors(error: ValidationError) -> str:
    parts = []
    for item in error.errors()[:3]:
        where = ".".join(str(p) for p in item["loc"]) or "payload"
        parts.append(f"{where}: {item['msg']}")
    return "; ".join(parts)


def _normalise(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fill in the one default that is never ambiguous: minutes without a mode means minutes."""
    if action_type == "timer.set" and "mode" not in payload and "minutes" in payload:
        return {**payload, "mode": "minutes"}
    return payload


def check_actions(items: list[Any], context: PlannerContext) -> Checked:
    """Keep the actions that pass the allowlist and payload checks; describe the rest."""
    out = Checked([], [], [])
    for item in items:
        if len(out.kept) >= MAX_ACTIONS:
            out.dropped.append(f"steps after the first {MAX_ACTIONS}")
            break
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            out.dropped.append("a step that wasn't an action")
            out.problems.append("every action must be an object with a type")
            continue
        action_type = item["type"]
        if action_type not in AI_PAYLOADS:
            out.dropped.append(f"{action_type} (not allowed)")
            out.problems.append(f"{action_type} is not an allowed action type")
            continue
        # Accept {"type", "payload": {...}} and the flat {"type", "level": 30} form.
        raw_payload = item.get("payload")
        if raw_payload is None:
            raw_payload = {k: v for k, v in item.items() if k != "type"}
        if not isinstance(raw_payload, dict):
            out.dropped.append(f"{action_type} (bad details)")
            out.problems.append(f"{action_type}: payload must be an object")
            continue
        try:
            model = AI_PAYLOADS[action_type].model_validate(_normalise(action_type, raw_payload))
        except ValidationError as exc:
            out.dropped.append(f"{action_type} (bad details)")
            out.problems.append(f"{action_type}: {_describe_errors(exc)}")
            continue
        action = AiAction(
            type=action_type, payload=model.model_dump(by_alias=True, exclude_none=True)
        )
        problem = _check_ids(action, context)
        if problem is not None:
            out.dropped.append(f"{action_type} ({problem})")
            out.problems.append(f"{action_type}: {problem}; use an id from the context")
            continue
        out.kept.append(action)
    return out


def validate_actions(items: list[Any], context: PlannerContext) -> tuple[list[AiAction], list[str]]:
    checked = check_actions(items, context)
    return checked.kept, checked.dropped


def needs_confirm(actions: list[AiAction], context: PlannerContext) -> bool:
    """Power actions, long typing and launching programs wait for the person to approve."""
    app_ids = {s["id"] for s in context.shortcuts if s.get("kind") == "app"}
    for action in actions:
        if action.type == "power.action":
            return True
        if action.type == "key.text" and len(action.payload.get("text", "")) > LONG_TEXT:
            return True
        if action.type == "launch.open" and action.payload.get("shortcutId") in app_ids:
            return True
    return False


def _reply_text(data: dict[str, Any], actions: list[AiAction], dropped: list[str]) -> str:
    reply = data.get("reply")
    text = reply.strip() if isinstance(reply, str) and reply.strip() else ""
    if not text:
        text = "Done." if actions else NOT_UNDERSTOOD
    if dropped:
        count = len(dropped)
        text = f"{text} I left out {count} step{'s' if count > 1 else ''} I can't do."
    return text[:MAX_REPLY]


class Planner:
    def __init__(self, provider: ChatProvider) -> None:
        self.provider = provider

    async def plan(self, text: str, context: PlannerContext) -> PlanDraft:
        """Ask the model, with one second try when the answer is broken or has bad steps."""
        system = build_system_prompt(context)
        messages = [ChatMessage("user", text)]
        try:
            raw = await self.provider.complete(system, messages)
            data, checked, feedback = self._read(raw, context)
            if feedback is not None:
                messages += [ChatMessage("assistant", raw[:2000]), ChatMessage("user", feedback)]
                try:
                    retry_raw = await self.provider.complete(system, messages)
                except ProviderError:
                    if data is None:
                        raise
                    retry_raw = ""
                retry_data, retry_checked, _ = self._read(retry_raw, context)
                # Keep the first answer if the second one is no better (or never came).
                if retry_data is not None and (
                    data is None or len(retry_checked.problems) < len(checked.problems)
                ):
                    data, checked = retry_data, retry_checked
        except ProviderError as exc:
            raise ActionError(exc.message) from exc
        if data is None:
            raise ActionError(NOT_UNDERSTOOD)
        return PlanDraft(
            reply=_reply_text(data, checked.kept, checked.dropped),
            actions=checked.kept,
            dropped=checked.dropped,
            needs_confirm=needs_confirm(checked.kept, context),
        )

    @staticmethod
    def _read(
        raw: str, context: PlannerContext
    ) -> tuple[dict[str, Any] | None, Checked, str | None]:
        """Parse and check one answer. The last item is feedback for a retry, if one is needed."""
        try:
            data = _loads(raw)
        except MalformedPlanError:
            return (
                None,
                Checked([], [], ["not a JSON object"]),
                "That wasn't a valid JSON object. Answer again with only the JSON object "
                '{"reply": ..., "actions": [...]}.',
            )
        checked = check_actions(data.get("actions", []), context)
        if not checked.problems:
            return data, checked, None
        feedback = (
            "Some actions were not valid: "
            + " | ".join(checked.problems[:6])
            + ". Answer again with the whole corrected JSON object, using only the allowed "
            "actions and values."
        )
        return data, checked, feedback

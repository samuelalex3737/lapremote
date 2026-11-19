"""protocol.py must match docs/PROTOCOL.md and the committed shared/protocol.schema.json.

The web side (web/tests/unit/protocol.sync.test.ts) checks protocol.ts against the
same two files, so both sides are held to one contract.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from lapremote import protocol
from lapremote.protocol import (
    AGENT_MESSAGES,
    CLIENT_MESSAGES,
    SCHEMA_PATH,
    MediaArtwork,
    MediaArtworkRequest,
    MediaSession,
    encode,
    render_schema,
)

DOC = Path(__file__).resolve().parents[2] / "docs" / "PROTOCOL.md"


def doc_types(direction: str) -> list[str]:
    text = DOC.read_text(encoding="utf-8")
    match = re.search(rf"```text {direction}\n(.*?)```", text, re.DOTALL)
    assert match, f"PROTOCOL.md has no '{direction}' block"
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def test_client_types_match_protocol_doc() -> None:
    documented = doc_types("client-to-agent")
    assert len(documented) == len(set(documented))
    assert sorted(documented) == sorted(CLIENT_MESSAGES)


def test_agent_types_match_protocol_doc() -> None:
    documented = doc_types("agent-to-client")
    assert len(documented) == len(set(documented))
    assert sorted(documented) == sorted(AGENT_MESSAGES)


def test_committed_schema_is_up_to_date() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render_schema(), (
        "run: uv run python -m lapremote.protocol --write"
    )


def test_media_artwork_exists_in_both_directions() -> None:
    assert CLIENT_MESSAGES["media.artwork"].payload is MediaArtworkRequest
    assert CLIENT_MESSAGES["media.artwork"].reply == "reply"
    assert AGENT_MESSAGES["media.artwork"] is MediaArtwork
    schema = json.loads(render_schema())
    assert schema["clientToAgent"]["media.artwork"]["payload"] == {
        "object": {"artworkId": {"required": True, "schema": {"type": "string"}}}
    }
    agent_side = schema["agentToClient"]["media.artwork"]["payload"]["object"]
    assert set(agent_side) == {"artworkId", "artwork"}


def test_media_session_has_artwork_id() -> None:
    fields = {f.alias or name for name, f in MediaSession.model_fields.items()}
    assert {"artworkId", "artwork"} <= fields


def test_every_payload_rejects_unknown_fields() -> None:
    for name, spec in CLIENT_MESSAGES.items():
        assert spec.payload.model_config.get("extra") == "forbid", name


def test_encode_uses_camel_case_envelope() -> None:
    text = encode("media.artwork", MediaArtwork(artwork_id="abc", artwork=None), "s1")
    assert json.loads(text) == {
        "v": 1,
        "id": "s1",
        "type": "media.artwork",
        "payload": {"artworkId": "abc", "artwork": None},
    }


def test_encode_rejects_client_only_types() -> None:
    with pytest.raises(KeyError):
        encode("auth.pair", MediaArtwork(artwork_id="a", artwork=None), "s1")


def test_seek_needs_exactly_one_of_to_or_by() -> None:
    seek = CLIENT_MESSAGES["media.seek"].payload
    seek.model_validate({"by": -120})
    seek.model_validate({"to": 30, "sessionId": "x"})
    for bad in ({}, {"to": 1, "by": 1}):
        with pytest.raises(ValidationError):
            seek.model_validate(bad)


def test_timer_minutes_required_for_minutes_mode() -> None:
    timer = CLIENT_MESSAGES["timer.set"].payload
    timer.model_validate({"mode": "end_of_media", "then": "pause"})
    with pytest.raises(ValidationError):
        timer.model_validate({"mode": "minutes", "then": "pause"})


def test_key_names_are_allowlisted() -> None:
    press = CLIENT_MESSAGES["key.press"].payload
    press.model_validate({"key": "f5", "modifiers": ["ctrl", "shift"]})
    for bad in ({"key": "F5"}, {"key": "cmd.exe"}, {"key": "a", "modifiers": ["ctrl", "ctrl"]}):
        with pytest.raises(ValidationError):
            press.model_validate(bad)


def test_shortcut_rules() -> None:
    save = CLIENT_MESSAGES["shortcuts.save"].payload
    save.model_validate(
        {"shortcut": {"id": "yt", "name": "YouTube", "kind": "url", "url": "https://youtube.com"}}
    )
    for bad in (
        {"id": "x", "name": "X", "kind": "url", "url": "javascript:alert(1)"},
        {"id": "x", "name": "X", "kind": "app"},
        {"id": "../x", "name": "X", "kind": "url", "url": "https://a.b"},
    ):
        with pytest.raises(ValidationError):
            save.model_validate({"shortcut": bad})


def test_ai_actions_are_allowlisted() -> None:
    protocol.AiAction.model_validate({"type": "volume.set", "payload": {"level": 30}})
    for bad in ("auth.pair", "devices.revoke", "shell.run"):
        with pytest.raises(ValidationError):
            protocol.AiAction.model_validate({"type": bad, "payload": {}})


def test_cli_check_and_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "shared" / "protocol.schema.json"
    monkeypatch.setattr(protocol, "SCHEMA_PATH", target)
    assert protocol.main(["--check"]) == 1
    assert protocol.main(["--write"]) == 0
    assert protocol.main(["--check"]) == 0
    assert protocol.main([]) == 2

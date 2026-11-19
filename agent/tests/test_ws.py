from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from lapremote.security.pairing import PairingManager
from lapremote.security.ratelimit import Limits

from .wsclient import agent_of, make_app, pair_new, phone


@pytest.fixture
def app(isolated_home: Path) -> FastAPI:
    return make_app(isolated_home)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_pair_success_returns_token_once_and_stores_only_hash(
    app: FastAPI, client: TestClient, isolated_home: Path
) -> None:
    code = agent_of(app).pairing.current()[0]
    with phone(client) as p:
        reply = p.pair(code)
        assert reply["type"] == "auth.ok"
        payload = reply["payload"]
        assert payload["role"] == "owner"
        assert payload["os"] in ("windows", "macos", "linux")
        assert payload["hostName"]
        assert len(payload["token"]) >= 40
        assert set(payload["features"]) >= {"input", "media", "secureContext"}
        # Owner gets the device list pushed after auth.
        devices = p.recv_type("devices.state")["payload"]["devices"]
        assert [d["deviceId"] for d in devices] == [payload["deviceId"]]
        assert devices[0]["online"] is True
    stored = (isolated_home / "devices.json").read_text(encoding="utf-8")
    assert payload["token"] not in stored
    assert "tokenHash" not in stored  # snake_case on disk
    assert json.loads(stored)["devices"][0]["token_hash"]


def test_second_device_is_guest(app: FastAPI, client: TestClient) -> None:
    assert pair_new(client, app)[2] == "owner"
    assert pair_new(client, app, "Second")[2] == "guest"


def test_expired_code_is_rejected(app: FastAPI, client: TestClient) -> None:
    now = [1000.0]
    agent = agent_of(app)
    agent.pairing = PairingManager(ttl=300, clock=lambda: now[0])
    code = agent.pairing.current()[0]
    now[0] += 301
    with phone(client) as p:
        reply = p.pair(code)
    assert reply == {
        "v": 1,
        "id": reply["id"],
        "type": "auth.fail",
        "payload": {"reason": "expired_code"},
    }


def test_reused_code_is_rejected(app: FastAPI, client: TestClient) -> None:
    code = agent_of(app).pairing.current()[0]
    with phone(client) as p:
        assert p.pair(code)["type"] == "auth.ok"
    with phone(client) as p:
        reply = p.pair(code)
    assert reply["type"] == "auth.fail"
    assert reply["payload"]["reason"] == "invalid_code"


def test_wrong_code_is_rejected(app: FastAPI, client: TestClient) -> None:
    code = agent_of(app).pairing.current()[0]
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    with phone(client) as p:
        assert p.pair(wrong)["payload"]["reason"] == "invalid_code"


def test_resume_with_good_and_bad_token(app: FastAPI, client: TestClient) -> None:
    device_id, token, _ = pair_new(client, app)
    with phone(client) as p:
        reply = p.resume(device_id, token)
        assert reply["type"] == "auth.ok"
        assert reply["payload"]["token"] is None
    with phone(client) as p:
        reply = p.resume(device_id, token[:-2] + "xx")
    assert reply["payload"] == {"reason": "bad_token"}
    with phone(client) as p:
        assert p.resume("unknown-device", token)["payload"] == {"reason": "bad_token"}


def test_messages_before_auth_are_rejected(client: TestClient) -> None:
    with phone(client) as p:
        msg_id = p.send("ping", {"t": 1})
        assert p.ack_for(msg_id) == {"id": msg_id, "ok": False, "error": "Pair this phone first."}
        msg_id = p.send("media.toggle", {})
        assert p.ack_for(msg_id)["ok"] is False


def test_auth_messages_after_auth_are_rejected(app: FastAPI, client: TestClient) -> None:
    device_id, token, _ = pair_new(client, app)
    with phone(client) as p:
        p.resume(device_id, token)
        msg_id = p.send("auth.resume", {"deviceId": device_id, "token": token})
        assert p.ack_for(msg_id)["error"] == "Already connected."


def test_socket_closes_without_auth(isolated_home: Path) -> None:
    app = make_app(isolated_home, auth_timeout=0.2)
    with TestClient(app) as client, phone(client) as p:
        with pytest.raises(WebSocketDisconnect) as exc:
            p.recv()
        assert exc.value.code == 4001


@pytest.mark.parametrize("origin", ["http://evil.example", "http://testserver:8080", "null", ""])
def test_bad_origin_is_refused(client: TestClient, origin: str) -> None:
    with pytest.raises(WebSocketDisconnect) as exc, phone(client, origin=origin):
        pass
    assert exc.value.code == 4003


def test_guest_cannot_use_owner_messages(app: FastAPI, client: TestClient) -> None:
    pair_new(client, app)
    device_id, token, role = pair_new(client, app, "Guest")
    assert role == "guest"
    with phone(client) as p:
        p.resume(device_id, token)
        msg_id = p.send("devices.list", {})
        assert p.ack_for(msg_id)["error"] == "Only the owner can do that."
        msg_id = p.send("input.click", {"button": "left"})
        assert p.ack_for(msg_id)["error"] == "Only the owner can do that."
        # Guests may ping.
        p.send("ping", {"t": 5})
        assert p.recv_type("pong")["payload"] == {"t": 5}


def test_malformed_input_never_closes_the_socket(app: FastAPI, client: TestClient) -> None:
    device_id, token, _ = pair_new(client, app)
    with phone(client) as p:
        p.resume(device_id, token)
        p.send_raw("{not json")
        assert p.recv_type("ack")["payload"] == {
            "id": "",
            "ok": False,
            "error": "That message wasn't valid.",
        }
        p.send_raw(json.dumps({"v": 2, "id": "x1", "type": "ping", "payload": {}}))
        assert p.ack_for("x1")["ok"] is False
        bad = p.send("ping", {"t": "soon"})
        ack = p.ack_for(bad)
        assert ack["ok"] is False
        assert ack["error"].startswith("Invalid t")
        extra = p.send("ping", {"t": 1, "sneaky": True})
        assert p.ack_for(extra)["ok"] is False
        unknown = p.send("shell.exec", {"cmd": "calc"})
        assert p.ack_for(unknown)["error"] == "Unknown request."
        key = p.send("key.press", {"key": "rm -rf", "modifiers": []})
        assert p.ack_for(key)["ok"] is False
        p.ws.send_bytes(b"\x00\x01")
        assert p.recv_type("ack")["payload"]["ok"] is False
        p.send("ping", {"t": 42})
        assert p.recv_type("pong")["payload"] == {"t": 42}


def test_unimplemented_feature_is_reported(app: FastAPI, client: TestClient) -> None:
    device_id, token, _ = pair_new(client, app)
    with phone(client) as p:
        p.resume(device_id, token)
        msg_id = p.send("brightness.set", {"level": 50})
        assert p.ack_for(msg_id)["error"] == "That isn't available on this laptop yet."


def test_pairing_attempts_are_rate_limited(app: FastAPI, client: TestClient) -> None:
    with phone(client) as p:
        reasons = [p.pair("000000")["payload"]["reason"] for _ in range(6)]
    assert reasons[:5] == ["invalid_code"] * 5 or reasons[:5].count("invalid_code") == 5
    assert reasons[5] == "rate_limited"
    # Even the right code is refused while limited.
    code = agent_of(app).pairing.current()[0]
    with phone(client) as p:
        assert p.pair(code)["payload"]["reason"] == "rate_limited"


def test_general_rate_limit(isolated_home: Path) -> None:
    app = make_app(isolated_home, limits=Limits(messages_per_second=5))
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            ids = [p.send("ping", {"t": n}) for n in range(30)]
            limited = 0
            for _ in range(len(ids) + 5):
                message = p.recv()
                if message["type"] == "ack" and message["payload"]["error"] == (
                    "Too many requests. Slow down a little."
                ):
                    limited += 1
                if (
                    message["type"] in ("pong", "ack")
                    and message["payload"].get("id", None) == ids[-1]
                ):
                    break
                if message["type"] == "pong" and message["payload"]["t"] == 29:
                    break
    assert limited >= 20


def test_key_text_rate_limit(isolated_home: Path) -> None:
    app = make_app(isolated_home, limits=Limits(key_text_per_second=2))
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            errors = [p.ack_for(p.send("key.text", {"text": "hi"}))["error"] for _ in range(4)]
    assert errors.count("Too many requests. Slow down a little.") >= 2


def test_revoke_closes_the_device_and_kills_its_token(app: FastAPI, client: TestClient) -> None:
    owner_id, owner_token, _ = pair_new(client, app)
    guest_id, guest_token, _ = pair_new(client, app, "Guest")
    with phone(client) as owner, phone(client) as guest:
        owner.resume(owner_id, owner_token)
        guest.resume(guest_id, guest_token)
        msg_id = owner.send("devices.revoke", {"deviceId": guest_id})
        assert owner.ack_for(msg_id)["ok"] is True
        with pytest.raises(WebSocketDisconnect) as exc:
            for _ in range(10):
                guest.recv()
        assert exc.value.code == 4003
        owner.send("devices.list", {})
        state = owner.recv_type("devices.state")["payload"]["devices"]
        while len(state) != 1:
            state = owner.recv_type("devices.state")["payload"]["devices"]
        assert [d["deviceId"] for d in state] == [owner_id]
    with phone(client) as p:
        assert p.resume(guest_id, guest_token)["payload"] == {"reason": "bad_token"}


def test_last_owner_cannot_be_removed_or_demoted(app: FastAPI, client: TestClient) -> None:
    owner_id, owner_token, _ = pair_new(client, app)
    pair_new(client, app, "Guest")
    with phone(client) as p:
        p.resume(owner_id, owner_token)
        msg_id = p.send("devices.role", {"deviceId": owner_id, "role": "guest"})
        assert p.ack_for(msg_id)["error"] == "Make another device the owner first."
        msg_id = p.send("devices.revoke", {"deviceId": owner_id})
        assert p.ack_for(msg_id)["error"] == "Make another device the owner first."
        msg_id = p.send("devices.revoke", {"deviceId": "nope"})
        assert p.ack_for(msg_id)["error"] == "That device isn't paired."


def test_promote_guest_notifies_it(app: FastAPI, client: TestClient) -> None:
    owner_id, owner_token, _ = pair_new(client, app)
    guest_id, guest_token, _ = pair_new(client, app, "Guest")
    with phone(client) as owner, phone(client) as guest:
        owner.resume(owner_id, owner_token)
        guest.resume(guest_id, guest_token)
        msg_id = owner.send("devices.role", {"deviceId": guest_id, "role": "owner"})
        assert owner.ack_for(msg_id)["ok"] is True
        toast = guest.recv_type("toast")["payload"]
        assert toast == {"level": "info", "message": "You're now an owner of this laptop."}
        # The promoted device can now use owner messages without reconnecting.
        guest.send("devices.list", {})
        assert guest.recv_type("devices.state")


def test_logs_never_contain_secrets(app: FastAPI, client: TestClient, isolated_home: Path) -> None:
    code = agent_of(app).pairing.current()[0]
    with phone(client) as p:
        reply = p.pair(code)
        token = reply["payload"]["token"]
        p.recv_type("devices.state")
        secret_text = "my secret password 123"
        msg_id = p.send("key.text", {"text": secret_text})
        p.ack_for(msg_id)
    log_text = (isolated_home / "logs" / "agent.log").read_text(encoding="utf-8")
    assert token not in log_text
    assert code not in log_text
    assert secret_text not in log_text
    entries = [json.loads(line) for line in log_text.splitlines()]
    key_entries = [e for e in entries if e.get("type") == "key.text"]
    assert key_entries
    assert key_entries[0]["textLength"] == len(secret_text)
    assert all("ts" in e and "level" in e for e in entries)

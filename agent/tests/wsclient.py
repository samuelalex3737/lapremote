"""Helpers for driving the agent's /ws endpoint in tests."""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from lapremote.config import Config
from lapremote.core import Agent
from lapremote.input.service import InputDevices, detect_input_devices
from lapremote.media.base import MediaBackend, NoSessionBackend
from lapremote.security.ratelimit import Limits
from lapremote.server import create_app
from lapremote.system.context import ForegroundReader
from lapremote.system.volume import VolumeBackend

from .fakes import FakeVolume

ORIGIN = "http://testserver"


def make_app(
    home: Path,
    *,
    limits: Limits | None = None,
    auth_timeout: float = 5.0,
    static_dir: Path | None = None,
    input_devices: InputDevices | None = None,
    media_backend: MediaBackend | None = None,
    volume_backend: VolumeBackend | None = None,
    foreground_reader: ForegroundReader | None = None,
) -> FastAPI:
    # Never inject real input from tests: default to the dry-run backend.
    devices = input_devices or detect_input_devices("windows", None, dry_run=True)
    return create_app(
        Config(),
        home=home,
        static_dir=static_dir or home / "no-static",
        lan_ip="127.0.0.1",
        advertise=False,
        print_banner=False,
        console_log=False,
        limits=limits,
        auth_timeout=auth_timeout,
        input_devices=devices,
        # Never touch the real media sessions or system volume from tests by default.
        media_backend=media_backend or NoSessionBackend(),
        volume_backend=volume_backend or FakeVolume(),
        # Tests never read the real foreground window unless they pass a reader.
        foreground_reader=foreground_reader,
    )


def agent_of(app: FastAPI) -> Agent:
    agent: Agent = app.state.agent
    return agent


class Phone:
    """A fake phone speaking the LapRemote protocol over a TestClient WebSocket."""

    def __init__(self, ws: WebSocketTestSession) -> None:
        self.ws = ws
        self._ids = itertools.count(1)

    def send(self, type_: str, payload: dict[str, Any] | None = None) -> str:
        msg_id = f"c{next(self._ids)}"
        self.ws.send_text(
            json.dumps({"v": 1, "id": msg_id, "type": type_, "payload": payload or {}})
        )
        return msg_id

    def send_raw(self, text: str) -> None:
        self.ws.send_text(text)

    def recv(self) -> dict[str, Any]:
        message: dict[str, Any] = self.ws.receive_json()
        return message

    def recv_type(self, type_: str, limit: int = 20) -> dict[str, Any]:
        for _ in range(limit):
            message = self.recv()
            if message["type"] == type_:
                return message
        msg = f"no {type_!r} message within {limit} messages"
        raise AssertionError(msg)

    def ack_for(self, msg_id: str, limit: int = 20) -> dict[str, Any]:
        for _ in range(limit):
            message = self.recv()
            if message["type"] == "ack" and message["payload"]["id"] == msg_id:
                payload: dict[str, Any] = message["payload"]
                return payload
        msg = f"no ack for {msg_id}"
        raise AssertionError(msg)

    def ack_with(self, msg_id: str, limit: int = 20) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """The ack for msg_id plus every other message that arrived before it."""
        others: list[dict[str, Any]] = []
        for _ in range(limit):
            message = self.recv()
            if message["type"] == "ack" and message["payload"]["id"] == msg_id:
                payload: dict[str, Any] = message["payload"]
                return payload, others
            others.append(message)
        msg = f"no ack for {msg_id}"
        raise AssertionError(msg)

    def pair(self, code: str, name: str = "Test phone") -> dict[str, Any]:
        self.send("auth.pair", {"code": code, "deviceName": name, "platform": "ios"})
        return self.recv()

    def resume(self, device_id: str, token: str) -> dict[str, Any]:
        self.send("auth.resume", {"deviceId": device_id, "token": token})
        return self.recv()


@contextmanager
def phone(client: TestClient, origin: str = ORIGIN) -> Iterator[Phone]:
    with client.websocket_connect("/ws", headers={"origin": origin}) as ws:
        yield Phone(ws)


def pair_new(client: TestClient, app: FastAPI, name: str = "Test phone") -> tuple[str, str, str]:
    """Pair a device and return (device_id, token, role)."""
    code = agent_of(app).pairing.current()[0]
    with phone(client) as p:
        reply = p.pair(code, name)
    assert reply["type"] == "auth.ok", reply
    payload = reply["payload"]
    return payload["deviceId"], payload["token"], payload["role"]

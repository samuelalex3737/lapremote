"""End to end over a real socket: a tiny Python client pairs, resumes and pings.

The agent runs in uvicorn on a free port in a background thread.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from websockets.sync.client import ClientConnection, connect
from websockets.typing import Origin

from .wsclient import agent_of, make_app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


class LiveAgent:
    def __init__(self, home: Path) -> None:
        self.app = make_app(home)
        self.port = free_port()
        config = uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> LiveAgent:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                msg = "agent did not start"
                raise RuntimeError(msg)
            time.sleep(0.05)
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

    @property
    def base(self) -> str:
        return f"127.0.0.1:{self.port}"


class TinyClient:
    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws
        self.n = 0

    def send(self, type_: str, payload: dict[str, Any]) -> None:
        self.n += 1
        self.ws.send(json.dumps({"v": 1, "id": f"t{self.n}", "type": type_, "payload": payload}))

    def recv(self, type_: str) -> dict[str, Any]:
        while True:
            message: dict[str, Any] = json.loads(self.ws.recv(timeout=5))
            if message["type"] == type_:
                return message


@pytest.fixture
def live(isolated_home: Path) -> Iterator[LiveAgent]:
    with LiveAgent(isolated_home) as agent:
        yield agent


def open_ws(live: LiveAgent) -> ClientConnection:
    return connect(f"ws://{live.base}/ws", origin=Origin(f"http://{live.base}"))


def test_pair_then_resume_then_ping(live: LiveAgent) -> None:
    assert httpx.get(f"http://{live.base}/api/health").json()["ok"] is True
    code = agent_of(live.app).pairing.current()[0]

    with open_ws(live) as ws:
        client = TinyClient(ws)
        client.send("auth.pair", {"code": code, "deviceName": "Pixel", "platform": "android"})
        ok = client.recv("auth.ok")["payload"]
        device_id, token = ok["deviceId"], ok["token"]
        assert ok["role"] == "owner"

    with open_ws(live) as ws:
        client = TinyClient(ws)
        client.send("auth.resume", {"deviceId": device_id, "token": token})
        resumed = client.recv("auth.ok")["payload"]
        assert resumed["deviceId"] == device_id
        assert resumed["token"] is None
        rtts = []
        for _ in range(20):
            sent = time.perf_counter() * 1000
            client.send("ping", {"t": sent})
            pong = client.recv("pong")["payload"]
            assert pong["t"] == sent
            rtts.append(time.perf_counter() * 1000 - sent)
        assert max(rtts) < 500


def test_wrong_origin_is_refused_on_a_real_socket(live: LiveAgent) -> None:
    from websockets.exceptions import InvalidStatus  # noqa: PLC0415

    with pytest.raises(InvalidStatus) as exc:
        connect(f"ws://{live.base}/ws", origin=Origin("http://evil.example"))
    assert exc.value.response.status_code == 403

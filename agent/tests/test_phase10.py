"""Phase 10: idle cost and resilience."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from .fakes import FakeMediaBackend, FakeVolume
from .wsclient import make_app, pair_new, phone


def test_no_polling_while_no_phone_is_connected(isolated_home: Path) -> None:
    volume = FakeVolume(level=33)
    app = make_app(isolated_home, volume_backend=volume)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        time.sleep(0.1)
        before = volume.reads
        # Five poll periods with nobody connected: no reads at all.
        time.sleep(2.6)
        assert volume.reads == before
        volume.level = 61
        with phone(client) as p:
            p.resume(device_id, token)
            # The phone gets a fresh value, not the one cached before it connected.
            assert p.recv_type("volume.state")["payload"] == {"level": 61, "muted": False}
            time.sleep(1.2)
            assert volume.reads >= before + 2


# ---------------------------------------------------------------- resilience


def test_phone_resumes_after_the_agent_restarts(isolated_home: Path) -> None:
    first = make_app(isolated_home)
    with TestClient(first) as client:
        device_id, token, _ = pair_new(client, first)
    # A new agent process on the same data folder: the phone's saved token still works.
    second = make_app(isolated_home)
    with TestClient(second) as client, phone(client) as p:
        ok = p.resume(device_id, token)
        assert ok["type"] == "auth.ok"
        assert ok["payload"]["role"] == "owner"


def test_broken_devices_file_fails_closed(isolated_home: Path) -> None:
    isolated_home.mkdir(parents=True, exist_ok=True)
    (isolated_home / "devices.json").write_text("{not json", encoding="utf-8")
    app = make_app(isolated_home)
    with TestClient(app) as client, phone(client) as p:
        refused = p.resume("someone", "any-token")
        assert refused["type"] == "auth.fail"
    assert (isolated_home / "devices.json.broken").read_text(encoding="utf-8") == "{not json"


def test_busy_port_gets_a_friendly_message() -> None:
    import socket  # noqa: PLC0415

    from lapremote import __main__ as entry  # noqa: PLC0415

    with socket.socket() as held:
        held.bind(("0.0.0.0", 0))
        held.listen()
        port = held.getsockname()[1]
        problem = entry.port_problem(port)
    assert problem is not None
    assert problem.startswith(f"port {port} is already in use.")
    assert entry.port_problem(port) is None


def test_volume_device_disappearing_does_not_break_the_agent(isolated_home: Path) -> None:
    volume = FakeVolume(level=40)
    app = make_app(isolated_home, volume_backend=volume)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            volume.broken = True
            time.sleep(1.2)
            p.send("ping", {"t": 9})
            assert p.recv_type("pong", limit=40)["payload"] == {"t": 9}
            volume.broken = False
            volume.level = 12
            assert p.recv_type("volume.state", limit=40)["payload"]["level"] == 12


class BrokenStartBackend(FakeMediaBackend):
    async def start(self) -> None:
        msg = "session manager unavailable"
        raise RuntimeError(msg)


def test_media_backend_failing_at_start_falls_back_to_media_keys(isolated_home: Path) -> None:
    app = make_app(isolated_home, media_backend=BrokenStartBackend())
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            ok = p.resume(device_id, token)
            media = ok["payload"]["features"]["media"]
            assert media == {"available": True, "reason": "Showing what's playing isn't available."}
            # Play/pause still works through the OS media keys (dry-run input here).
            assert p.ack_for(p.send("media.toggle", {}))["ok"] is True

"""The laptop's Wi-Fi address changing: remembered, watched, shown and acted on."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lapremote import __main__ as entry
from lapremote import netwatch, server
from lapremote.netwatch import NETWORK_FILE, AddressMemory, Move, NetworkWatch
from lapremote.security.pairing import DeviceStore
from lapremote.tray import TrayController

from .fakes import FakeAutostart
from .test_phase9 import LOCAL, FakeIcon, _free_port
from .wsclient import agent_of, make_app, pair_new


def _watch(tmp_path: Path, answers: list[str | None]) -> NetworkWatch:
    def detect() -> str | None:
        return answers.pop(0)

    return NetworkWatch(AddressMemory(tmp_path / NETWORK_FILE), detect, every=0.01)


# ---------------------------------------------------------------- memory


def test_memory_remembers_and_reports_a_change(tmp_path: Path) -> None:
    memory = AddressMemory(tmp_path / NETWORK_FILE)
    assert memory.last() is None
    assert memory.record("192.168.1.33") is None  # nothing to compare with yet
    assert memory.record("192.168.1.33") is None
    assert memory.record("172.20.82.96") == Move("192.168.1.33", "172.20.82.96")
    assert memory.last() == "172.20.82.96"
    saved = json.loads((tmp_path / NETWORK_FILE).read_text(encoding="utf-8"))
    assert saved == {"lanIp": "172.20.82.96"}


@pytest.mark.parametrize("content", ["{not json", "[]", '{"lanIp": 5}', '{"lanIp": ""}'])
def test_a_broken_memory_file_counts_as_none(tmp_path: Path, content: str) -> None:
    (tmp_path / NETWORK_FILE).write_text(content, encoding="utf-8")
    memory = AddressMemory(tmp_path / NETWORK_FILE)
    assert memory.last() is None
    assert memory.record("10.0.0.4") is None
    assert memory.last() == "10.0.0.4"


# ---------------------------------------------------------------- watch


def test_watch_tells_listeners_once_per_change(tmp_path: Path) -> None:
    async def scenario() -> None:
        watch = _watch(tmp_path, [None, "192.168.1.33", "172.20.82.96", "172.20.82.96"])
        seen: list[Move] = []
        awaited: list[str] = []

        def broken(_move: Move) -> None:
            raise RuntimeError("listener bug")

        async def slow(move: Move) -> None:
            await asyncio.sleep(0)
            awaited.append(move.current)

        watch.on_move(broken)  # one failing listener must not stop the others
        watch.on_move(seen.append)
        watch.on_move(slow)
        await watch.start("192.168.1.33")
        assert seen == []  # first ever address: nothing to compare with
        assert await watch.check() is None  # offline keeps the last address
        assert watch.ip == "192.168.1.33"
        assert await watch.check() is None  # back on the same network
        move = await watch.check()
        assert move == Move("192.168.1.33", "172.20.82.96")
        assert await watch.check() is None
        assert seen == [move]
        assert awaited == ["172.20.82.96"]
        assert watch.ip == "172.20.82.96"
        assert watch.moved == move

    asyncio.run(scenario())


def test_watch_notices_a_new_network_at_startup(tmp_path: Path) -> None:
    async def scenario() -> None:
        AddressMemory(tmp_path / NETWORK_FILE).record("192.168.1.33")
        watch = _watch(tmp_path, [])
        seen: list[Move] = []
        watch.on_move(seen.append)
        await watch.start("172.20.82.96")
        assert seen == [Move("192.168.1.33", "172.20.82.96")]
        # Started offline: nothing is forgotten and nothing is reported.
        offline = _watch(tmp_path, [])
        offline.on_move(seen.append)
        await offline.start(None)
        assert len(seen) == 1
        assert AddressMemory(tmp_path / NETWORK_FILE).last() == "172.20.82.96"

    asyncio.run(scenario())


def test_watch_keeps_running_after_a_failed_check(tmp_path: Path) -> None:
    calls: list[int] = []

    def detect() -> str | None:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("adapter vanished")
        return "10.0.0.9"

    async def scenario() -> None:
        watch = NetworkWatch(AddressMemory(tmp_path / NETWORK_FILE), detect, every=0.01)
        task = asyncio.create_task(watch.run())
        for _ in range(200):
            if watch.ip == "10.0.0.9":
                break
            await asyncio.sleep(0.01)
        task.cancel()
        assert watch.ip == "10.0.0.9"

    asyncio.run(scenario())


# ---------------------------------------------------------------- running agent


def _wait_for(check: object, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if callable(check) and check():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


def test_a_change_while_running_updates_the_code_and_the_dashboard(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = ["192.168.1.33"]
    monkeypatch.setattr(server, "detect_lan_ip", lambda: answers[0])
    monkeypatch.setattr(netwatch, "CHECK_SECONDS", 0.02)
    app = make_app(isolated_home, lan_ip=None)
    with TestClient(app) as client:
        local = TestClient(app, **LOCAL)  # type: ignore[arg-type]
        state = local.get("/desktop/api/state").json()
        assert state["pairing"]["url"].startswith("http://192.168.1.33:7777/?pair=")
        assert state["networkMoved"] is None
        pair_new(client, app, "Android phone")

        answers[0] = "172.20.82.96"
        _wait_for(lambda: app.state.network.ip == "172.20.82.96")
        state = local.get("/desktop/api/state").json()
        assert state["pairing"]["url"].startswith("http://172.20.82.96:7777/?pair=")
        assert state["networkMoved"] == {"from": "192.168.1.33", "to": "172.20.82.96"}
    saved = json.loads((isolated_home / NETWORK_FILE).read_text(encoding="utf-8"))
    assert saved == {"lanIp": "172.20.82.96"}


def test_the_dashboard_note_needs_a_paired_phone(isolated_home: Path) -> None:
    # A new laptop owner has nothing to pair again: the welcome guide covers it.
    AddressMemory(isolated_home / NETWORK_FILE).record("192.168.1.33")
    app = make_app(isolated_home)  # starts at 127.0.0.1: a different address
    with TestClient(app):
        local = TestClient(app, **LOCAL)  # type: ignore[arg-type]
        state = local.get("/desktop/api/state").json()
        assert state["firstRun"] is True
        assert state["networkMoved"] is None
        assert app.state.network.moved == Move("192.168.1.33", "127.0.0.1")


def test_tray_opens_the_pairing_code_only_with_paired_phones(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    opened: list[str] = []
    with TestClient(app) as client:
        ctl = TrayController(
            agent_of(app), 7777, FakeAutostart(), lambda: None, open_url=opened.append
        )
        move = Move("192.168.1.33", "172.20.82.96")
        asyncio.run(ctl.on_network_move(move))
        assert opened == []
        pair_new(client, app, "Android phone")
        asyncio.run(ctl.on_network_move(move))
        assert opened == ["http://127.0.0.1:7777/desktop#pair-title"]


def test_tray_mode_opens_the_code_after_moving_networks(isolated_home: Path) -> None:
    # Paired at home, started somewhere else: the dashboard opens at the pairing code.
    DeviceStore(isolated_home / "devices.json").add("Android phone", "android")
    AddressMemory(isolated_home / NETWORK_FILE).record("192.168.1.33")
    port = _free_port()
    opened: list[str] = []
    code = entry.run_with_tray(
        port,
        {},
        make_app=lambda: make_app(isolated_home),
        make_icon=lambda ctl: FakeIcon(ctl, port),
        open_url=opened.append,
    )
    assert code == 0
    assert opened == [f"http://127.0.0.1:{port}/desktop#pair-title"]


def test_tray_mode_on_the_same_network_opens_nothing(isolated_home: Path) -> None:
    DeviceStore(isolated_home / "devices.json").add("Android phone", "android")
    AddressMemory(isolated_home / NETWORK_FILE).record("127.0.0.1")
    port = _free_port()
    opened: list[str] = []
    entry.run_with_tray(
        port,
        {},
        make_app=lambda: make_app(isolated_home),
        make_icon=lambda ctl: FakeIcon(ctl, port),
        open_url=opened.append,
    )
    assert opened == []


def test_wifi_connecting_after_login_is_announced_without_a_move(tmp_path: Path) -> None:
    # At login LapRemote can start before the Wi-Fi connects. When it does connect (same
    # network as last time) the laptop must be announced, but nothing needs pairing again.
    async def scenario() -> None:
        AddressMemory(tmp_path / NETWORK_FILE).record("172.20.82.96")
        watch = _watch(tmp_path, [None, "172.20.82.96", "172.20.82.96", None, "192.168.1.33"])
        addresses: list[str] = []
        moves: list[Move] = []
        watch.on_address(addresses.append)
        watch.on_move(moves.append)
        await watch.start(None)
        assert await watch.check() is None  # still offline
        assert addresses == []
        assert await watch.check() is None  # Wi-Fi up, same network: no move
        assert addresses == ["172.20.82.96"]
        assert await watch.check() is None  # nothing new
        assert await watch.check() is None  # offline again keeps the address
        assert watch.ip == "172.20.82.96"
        move = await watch.check()  # then another network
        assert addresses == ["172.20.82.96", "192.168.1.33"]
        assert moves == [move] == [Move("172.20.82.96", "192.168.1.33")]

    asyncio.run(scenario())


def test_starting_offline_shows_the_code_once_wifi_connects(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers: list[str | None] = [None]
    monkeypatch.setattr(server, "detect_lan_ip", lambda: answers[0])
    monkeypatch.setattr(netwatch, "CHECK_SECONDS", 0.02)
    app = make_app(isolated_home, lan_ip=None)
    with TestClient(app):
        local = TestClient(app, **LOCAL)  # type: ignore[arg-type]
        assert local.get("/desktop/api/state").json()["pairing"]["url"] is None
        answers[0] = "172.20.82.96"
        _wait_for(lambda: app.state.network.ip == "172.20.82.96")
        state = local.get("/desktop/api/state").json()
        assert state["pairing"]["url"].startswith("http://172.20.82.96:7777/?pair=")
        assert state["networkMoved"] is None

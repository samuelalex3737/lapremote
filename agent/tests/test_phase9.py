"""Phase 9: pause, the /desktop dashboard, start at login, the tray and tray mode."""

from __future__ import annotations

import json
import plistlib
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lapremote import __main__ as entry
from lapremote.autostart import (
    APP_NAME,
    LinuxAutostart,
    MacAutostart,
    WindowsAutostart,
    launch_command,
)
from lapremote.config import load_config
from lapremote.tray import TrayController, menu_entries, tray_image

from .fakes import FakeAutostart
from .test_input import recorder_devices
from .wsclient import agent_of, make_app, pair_new, phone

LOCAL = {"base_url": "http://127.0.0.1:7777", "client": ("127.0.0.1", 50123)}
WRITE = {"X-LapRemote-Desktop": "1", "Origin": "http://127.0.0.1:7777"}


@contextmanager
def running(app: FastAPI) -> Iterator[tuple[TestClient, TestClient]]:
    """A phone-side client (runs the lifespan) and a laptop-side client for /desktop."""
    with TestClient(app) as client:
        yield client, TestClient(app, **LOCAL)  # type: ignore[arg-type]


# ---------------------------------------------------------------- pause


def test_pause_refuses_control_but_keeps_phones_connected(isolated_home: Path) -> None:
    devices, rec = recorder_devices()
    app = make_app(isolated_home, input_devices=devices)
    with running(app) as (client, local):
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert local.post(
                "/desktop/api/pause", json={"paused": True}, headers=WRITE
            ).json() == {
                "ok": True,
                "paused": True,
            }
            toast = p.recv_type("toast")["payload"]
            assert toast == {"level": "warn", "message": "Remote control is paused on the laptop."}
            ack = p.ack_for(p.send("input.click", {"button": "left"}))
            assert ack["error"] == "Remote control is paused on the laptop."
            p.send("input.move", {"dx": 5, "dy": 5})
            p.send("ping", {"t": 3})
            assert p.recv_type("pong")["payload"] == {"t": 3}
            assert rec.calls == []

            local.post("/desktop/api/pause", json={"paused": False}, headers=WRITE)
            assert p.recv_type("toast")["payload"]["message"] == "Remote control is back on."
            assert p.ack_for(p.send("input.click", {"button": "left"}))["ok"] is True
    assert rec.calls
    # The setting is saved, so a restart keeps it.
    saved = json.loads((isolated_home / "config.json").read_text(encoding="utf-8"))
    assert saved["remoteControlPaused"] is False


# ---------------------------------------------------------------- dashboard access


def test_dashboard_is_only_for_the_laptop_itself(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with TestClient(app) as phone_side:
        # Another machine on the Wi-Fi.
        assert phone_side.get("/desktop").status_code == 404
        assert phone_side.get("/desktop/api/state").status_code == 404
        # Loopback, but a Host header that isn't localhost (DNS rebinding).
        rebind = TestClient(app, base_url="http://evil.example:7777", client=("127.0.0.1", 5))
        assert rebind.get("/desktop/api/state").status_code == 404
        local = TestClient(app, **LOCAL)  # type: ignore[arg-type]
        page = local.get("/desktop")
        assert page.status_code == 200
        csp = page.headers["content-security-policy"]
        nonce = csp.split("'nonce-")[1].split("'")[0]
        assert f'<script nonce="{nonce}">' in page.text
        assert "frame-ancestors 'none'" in csp
        assert page.headers["x-frame-options"] == "DENY"
        assert "__NONCE__" not in page.text
        assert (
            TestClient(app, base_url="http://localhost:7777", client=("::1", 5))
            .get("/desktop/api/state")
            .status_code
            == 200
        )


def test_dashboard_changes_need_the_header_and_a_local_origin(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with running(app) as (_client, local):
        before = agent_of(app).pairing.current()[0]
        assert local.post("/desktop/api/pair/regenerate").status_code == 403
        foreign = {"X-LapRemote-Desktop": "1", "Origin": "https://evil.example"}
        assert local.post("/desktop/api/pair/regenerate", headers=foreign).status_code == 403
        assert agent_of(app).pairing.current()[0] == before
        assert local.post("/desktop/api/pair/regenerate", headers=WRITE).json() == {"ok": True}
        assert agent_of(app).pairing.current()[0] != before


# ---------------------------------------------------------------- dashboard content


def test_dashboard_state(isolated_home: Path) -> None:
    autostart = FakeAutostart()
    app = make_app(isolated_home, autostart=autostart)
    with running(app) as (client, local):
        first = local.get("/desktop/api/state").json()
        assert first["firstRun"] is True
        code = agent_of(app).pairing.current()[0]
        assert first["pairing"]["code"] == code
        assert first["pairing"]["url"] == f"http://127.0.0.1:7777/?pair={code}"
        assert first["pairing"]["qrSvg"].startswith("<svg")
        assert "<script" not in first["pairing"]["qrSvg"]
        assert first["autostart"] is False
        assert first["paused"] is False
        names = [c["name"] for c in first["checklist"]]
        assert names[:3] == ["input", "media", "volume"]
        assert "https" in names
        assert first["settings"]["aiModel"] == "qwen2.5:7b"

        device_id, token, _ = pair_new(client, app, "Sam's <b>phone</b>")
        with phone(client) as p:
            p.resume(device_id, token)
            for _ in range(3):
                p.ack_for(p.send("volume.set", {"level": 20}))
            state = local.get("/desktop/api/state").json()
        assert state["firstRun"] is False
        [device] = state["devices"]
        # The name is passed through as data; the page sets it with textContent.
        assert device["name"] == "Sam's <b>phone</b>"
        assert device["online"] is True
        assert device["handlingMs"]["p50"] >= 0
        assert device["handlingMs"]["p95"] >= device["handlingMs"]["p50"]


def test_dashboard_device_actions(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with running(app) as (client, local):
        owner_id, owner_token, _ = pair_new(client, app, "Owner")
        guest_id, _guest_token, _ = pair_new(client, app, "Guest")
        last = local.post(f"/desktop/api/devices/{owner_id}/revoke", headers=WRITE)
        assert last.status_code == 400
        assert last.json() == {"error": "Make another device the owner first."}
        promoted = local.post(
            f"/desktop/api/devices/{guest_id}/role", json={"role": "owner"}, headers=WRITE
        )
        assert promoted.json() == {"ok": True}
        with phone(client) as p:
            p.resume(owner_id, owner_token)
            assert local.post(f"/desktop/api/devices/{owner_id}/revoke", headers=WRITE).json() == {
                "ok": True
            }
        roles = {d.device_id: d.role for d in agent_of(app).devices.list()}
        assert roles == {guest_id: "owner"}
        missing = local.post("/desktop/api/devices/nope/revoke", headers=WRITE)
        assert missing.json() == {"error": "That device isn't paired."}


def test_dashboard_autostart_and_settings(isolated_home: Path) -> None:
    autostart = FakeAutostart()
    app = make_app(isolated_home, autostart=autostart)
    with running(app) as (_client, local):
        on = local.post("/desktop/api/autostart", json={"enabled": True}, headers=WRITE)
        assert on.json() == {"ok": True, "enabled": True}
        assert autostart.enabled is True
        saved = local.post(
            "/desktop/api/settings",
            json={"aiModel": "qwen2.5:3b", "previewFps": 10, "preferredBrowser": "chrome"},
            headers=WRITE,
        )
        assert saved.json() == {
            "ok": True,
            "message": "Saved. Restart LapRemote to use the new settings.",
        }
        bad = local.post("/desktop/api/settings", json={"previewFps": 99}, headers=WRITE)
        assert bad.json() == {"error": "One of those values isn't allowed."}
        unknown = local.post("/desktop/api/settings", json={"port": 80}, headers=WRITE)
        assert unknown.status_code == 422
    config = load_config(isolated_home / "config.json")
    assert config.ai.model == "qwen2.5:3b"
    assert config.preview.fps == 10
    assert config.preferred_browser == "chrome"
    assert config.port == 7777


# ---------------------------------------------------------------- start at login


class FakeRegistry:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get(self, key: str, name: str) -> str | None:
        return self.values.get((key, name))

    def set(self, key: str, name: str, value: str) -> None:
        self.values[(key, name)] = value

    def delete(self, key: str, name: str) -> None:
        self.values.pop((key, name), None)


def test_windows_autostart_quotes_paths_with_spaces() -> None:
    registry = FakeRegistry()
    auto = WindowsAutostart(
        registry, [r"C:\Program Files\LapRemote\pythonw.exe", "-m", "lapremote"]
    )
    assert auto.is_enabled() is False
    auto.enable()
    value = registry.values[(r"Software\Microsoft\Windows\CurrentVersion\Run", APP_NAME)]
    assert value == r'"C:\Program Files\LapRemote\pythonw.exe" -m lapremote'
    assert auto.is_enabled() is True
    auto.disable()
    assert auto.is_enabled() is False
    auto.disable()  # already off: no error


def test_mac_and_linux_autostart_files(tmp_path: Path) -> None:
    mac = MacAutostart(tmp_path / "LaunchAgents", ["/Applications/LapRemote.app/LapRemote"])
    mac.enable()
    plist = plistlib.loads((tmp_path / "LaunchAgents" / "com.lapremote.agent.plist").read_bytes())
    assert plist["ProgramArguments"] == ["/Applications/LapRemote.app/LapRemote"]
    assert plist["RunAtLoad"] is True
    assert mac.is_enabled()
    mac.disable()
    assert not mac.is_enabled()

    linux = LinuxAutostart(tmp_path / "autostart", ["/opt/lap remote/python", "-m", "lapremote"])
    linux.enable()
    entry_text = (tmp_path / "autostart" / "lapremote.desktop").read_text(encoding="utf-8")
    assert "Exec='/opt/lap remote/python' -m lapremote" in entry_text
    assert entry_text.startswith("[Desktop Entry]\nType=Application\n")
    assert linux.is_enabled()
    linux.disable()
    assert not linux.is_enabled()


def test_launch_command_from_source() -> None:
    command = launch_command()
    assert command[1:] == ["-m", "lapremote"]
    if sys.platform == "win32":
        assert Path(command[0]).name.lower() in {"pythonw.exe", "python.exe"}


@pytest.mark.skipif(sys.platform != "win32", reason="real registry round trip is Windows only")
def test_real_registry_round_trip_on_a_scratch_key() -> None:
    import winreg  # noqa: PLC0415

    from lapremote.autostart import CurrentUserRegistry  # noqa: PLC0415

    scratch = r"Software\LapRemoteTest\Run"
    auto = WindowsAutostart(CurrentUserRegistry(), ["C:/x/LapRemote.exe"], key=scratch)
    try:
        auto.enable()
        assert auto.is_enabled()
        auto.disable()
        assert not auto.is_enabled()
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, scratch)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\LapRemoteTest")


# ---------------------------------------------------------------- tray


def test_tray_menu_and_actions(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    opened: list[str] = []
    folders: list[Path] = []
    stopped: list[bool] = []
    autostart = FakeAutostart()
    with TestClient(app):
        agent = agent_of(app)
        ctl = TrayController(
            agent,
            7777,
            autostart,
            lambda: stopped.append(True),
            open_url=opened.append,
            show_folder=folders.append,
        )
        entries = menu_entries(ctl)
        assert [e.label for e in entries] == [
            "Pair a phone...",
            "Devices...",
            "Pause remote control",
            "Open dashboard",
            "Start at login",
            "Open logs folder",
            "Quit LapRemote",
        ]
        by_label = {e.label: e for e in entries}
        by_label["Pair a phone..."].action()
        by_label["Open dashboard"].action()
        assert opened == [
            "http://127.0.0.1:7777/desktop#pair-title",
            "http://127.0.0.1:7777/desktop",
        ]
        by_label["Start at login"].action()
        assert autostart.enabled is True
        start = by_label["Start at login"]
        assert start.checked is not None and start.checked()
        by_label["Open logs folder"].action()
        assert folders == [isolated_home / "logs"]
        by_label["Quit LapRemote"].action()
        assert stopped == [True]
    assert tray_image().size == (64, 64)


def test_tray_problem_without_a_desktop() -> None:
    assert entry.tray_problem("linux", {}) == "no desktop session"
    if sys.platform == "win32":
        assert entry.tray_problem("win32", {}) is None


class FakeIcon:
    """Stands in for pystray.Icon: waits for the agent, checks it serves, then quits."""

    def __init__(self, ctl: TrayController, port: int) -> None:
        self.ctl = ctl
        self.port = port
        self.stopped = threading.Event()
        self.health: dict[str, Any] | None = None
        self.paused_after_toggle: bool | None = None

    def run(self) -> None:
        deadline = time.monotonic() + 15
        while self.ctl.loop is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.health = httpx.get(f"http://127.0.0.1:{self.port}/api/health", timeout=5).json()
        # A menu click from the tray thread reaches the agent's loop.
        self.ctl.toggle_pause()
        self.paused_after_toggle = self.ctl.agent.config.remote_control_paused
        self.ctl.quit()
        self.stopped.wait(5)

    def stop(self) -> None:
        self.stopped.set()


def _free_port() -> int:
    import socket  # noqa: PLC0415

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def test_tray_mode_serves_in_a_thread_and_quits(isolated_home: Path) -> None:
    port = _free_port()
    icons: list[FakeIcon] = []
    opened: list[str] = []

    def make_icon(ctl: TrayController) -> FakeIcon:
        icon = FakeIcon(ctl, port)
        icons.append(icon)
        return icon

    code = entry.run_with_tray(
        port,
        {},
        make_app=lambda: make_app(isolated_home),
        make_icon=make_icon,
        open_url=opened.append,
    )
    assert code == 0
    [icon] = icons
    assert icon.health is not None
    assert icon.health["ok"] is True
    assert icon.paused_after_toggle is True
    # First run (no phones yet): the dashboard opened with the welcome guide.
    assert opened == [f"http://127.0.0.1:{port}/desktop"]

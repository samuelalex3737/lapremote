from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from lapremote.input.keyboard import Keyboard, UnsupportedKeyError
from lapremote.input.mouse import Mouse
from lapremote.input.service import InputDevices, detect_input_devices
from lapremote.protocol import Button
from lapremote.system.dpi import enable_dpi_awareness
from lapremote.system.permissions import (
    MAC_ACCESSIBILITY_HELP,
    WAYLAND_HELP,
    InputPermission,
    input_permission,
)

from .wsclient import make_app, pair_new, phone


class Recorder:
    """Records backend calls for both the mouse and keyboard protocols."""

    def __init__(self, unsupported: frozenset[str] = frozenset()) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.unsupported = unsupported

    def move(self, dx: int, dy: int) -> None:
        self.calls.append(("move", dx, dy))

    def press(self, key: object) -> None:
        self.calls.append(("press", key))

    def release(self, key: object) -> None:
        self.calls.append(("release", key))

    def scroll(self, dx: float, dy: float) -> None:
        self.calls.append(("scroll", dx, dy))

    def resolve(self, name: str) -> object:
        if name in self.unsupported:
            raise UnsupportedKeyError(name)
        return name

    def type(self, text: str) -> None:
        self.calls.append(("type", text))


# ---------------------------------------------------------------- mouse


def test_move_carries_sub_pixel_remainder() -> None:
    rec = Recorder()
    mouse = Mouse(rec, "windows")
    for _ in range(3):
        mouse.move(0.4, -0.4)
    assert rec.calls == [("move", 1, -1)]
    mouse.move(0.8, -0.8)
    assert rec.calls[-1] == ("move", 1, -1)


def test_whole_pixel_moves_pass_straight_through() -> None:
    rec = Recorder()
    Mouse(rec, "windows").move(12, -7)
    assert rec.calls == [("move", 12, -7)]


def test_click_down_up_and_drag_lock_release() -> None:
    rec = Recorder()
    mouse = Mouse(rec, "windows")
    mouse.click("right")
    assert rec.calls == [("press", "right"), ("release", "right")]
    rec.calls.clear()
    mouse.down("left")
    mouse.down("left")  # second down is ignored
    assert mouse.held == frozenset({"left"})
    mouse.click("left")  # a click while held ends the drag instead of clicking
    assert rec.calls == [("press", "left"), ("release", "left")]
    assert mouse.held == frozenset()
    mouse.up("left")  # nothing held: no extra release
    assert len(rec.calls) == 2


def test_release_all() -> None:
    rec = Recorder()
    mouse = Mouse(rec, "windows")
    mouse.down("left")
    mouse.down("middle")
    mouse.release_all()
    assert sorted(c[1] for c in rec.calls if c[0] == "release") == ["left", "middle"]
    assert mouse.held == frozenset()


def test_scroll_windows_high_resolution_and_direction() -> None:
    rec = Recorder()
    mouse = Mouse(rec, "windows")
    mouse.scroll(0, 1)  # one notch, view down -> pynput negative dy
    assert rec.calls == [("scroll", 0, pytest.approx(-1.0))]
    rec.calls.clear()
    mouse.scroll(0, 0.004)  # under 1/120 notch: carried, not sent
    assert rec.calls == []
    mouse.scroll(0, 0.005)
    assert rec.calls == [("scroll", 0, pytest.approx(-1 / 120))]


def test_scroll_linux_whole_notches_with_carry() -> None:
    rec = Recorder()
    mouse = Mouse(rec, "linux")
    mouse.scroll(0.5, -0.5)
    assert rec.calls == []
    mouse.scroll(0.5, -0.5)
    assert rec.calls == [("scroll", 1.0, 1.0)]


def test_scroll_macos_units() -> None:
    rec = Recorder()
    Mouse(rec, "macos").scroll(0, 1)
    assert rec.calls == [("scroll", 0, -4.0)]


# ---------------------------------------------------------------- keyboard


def test_combo_presses_modifiers_around_the_key() -> None:
    rec = Recorder()
    Keyboard(rec, "windows").press("c", ["ctrl", "shift"])
    assert rec.calls == [
        ("press", "ctrl"),
        ("press", "shift"),
        ("press", "c"),
        ("release", "c"),
        ("release", "shift"),
        ("release", "ctrl"),
    ]


def test_meta_maps_to_cmd_key() -> None:
    rec = Recorder()
    Keyboard(rec, "windows").press("tab", ["meta"])
    assert rec.calls[0] == ("press", "cmd")


def test_modifiers_released_even_if_key_press_fails() -> None:
    class Failing(Recorder):
        def press(self, key: object) -> None:
            if key == "x":
                msg = "boom"
                raise OSError(msg)
            super().press(key)

    rec = Failing()
    with pytest.raises(OSError, match="boom"):
        Keyboard(rec, "windows").press("x", ["ctrl"])
    assert rec.calls == [("press", "ctrl"), ("release", "ctrl")]


def test_zoom_uses_ctrl_or_cmd() -> None:
    win, mac = Recorder(), Recorder()
    Keyboard(win, "windows").zoom("in")
    Keyboard(mac, "macos").zoom("out")
    assert win.calls[:2] == [("press", "ctrl"), ("press", "=")]
    assert mac.calls[:2] == [("press", "cmd"), ("press", "-")]


def test_keys_outside_the_allowlist_are_refused() -> None:
    with pytest.raises(UnsupportedKeyError):
        Keyboard(Recorder(), "windows").press("ctrl_l")


def test_type_text() -> None:
    rec = Recorder()
    Keyboard(rec, "windows").type_text("héllo\nworld")
    assert rec.calls == [("type", "héllo\nworld")]


# ---------------------------------------------------------------- permissions and DPI


def test_input_permission_matrix() -> None:
    assert input_permission("windows", None, mac_trusted=False) == InputPermission(True, None)
    assert input_permission("macos", None, mac_trusted=True).available
    assert input_permission("macos", None, mac_trusted=False) == InputPermission(
        False, MAC_ACCESSIBILITY_HELP
    )
    assert input_permission("linux", "x11", mac_trusted=False).available
    assert input_permission("linux", "wayland", mac_trusted=False) == InputPermission(
        False, WAYLAND_HELP
    )
    assert not input_permission("linux", "unknown", mac_trusted=False).available


def test_mac_help_explains_exact_steps() -> None:
    assert "System Settings" in MAC_ACCESSIBILITY_HELP
    assert "Accessibility" in MAC_ACCESSIBILITY_HELP


def test_dpi_awareness_is_set_once() -> None:
    first = enable_dpi_awareness()
    assert first in ("per_monitor", "system", "already", "unsupported", "not_windows")
    assert enable_dpi_awareness() == first


def test_unavailable_input_is_reported() -> None:
    devices = detect_input_devices("linux", "wayland")
    assert devices.mouse is None
    assert devices.permission.reason == WAYLAND_HELP


# ---------------------------------------------------------------- over the socket


def recorder_devices() -> tuple[InputDevices, Recorder]:
    rec = Recorder(unsupported=frozenset({"insert"}))
    devices = InputDevices(
        Mouse(rec, "windows"), Keyboard(rec, "windows"), InputPermission(True, None)
    )
    return devices, rec


def test_input_messages_reach_the_backend(isolated_home: Path) -> None:
    devices, rec = recorder_devices()
    app = make_app(isolated_home, input_devices=devices)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            p.send("input.move", {"dx": 10.5, "dy": -3})
            p.send("input.scroll", {"dx": 0, "dy": 1})
            assert p.ack_for(p.send("input.click", {"button": "left"}))["ok"] is True
            assert p.ack_for(p.send("input.zoom", {"dir": "in"}))["ok"] is True
            assert p.ack_for(p.send("key.press", {"key": "tab", "modifiers": ["alt"]}))["ok"]
            assert p.ack_for(p.send("key.text", {"text": "hello"}))["ok"] is True
            ack = p.ack_for(p.send("key.press", {"key": "insert"}))
            assert ack == {
                "id": ack["id"],
                "ok": False,
                "error": "The insert key isn't available on this laptop.",
            }
    assert ("move", 10, -3) in rec.calls
    assert ("scroll", 0, pytest.approx(-1.0)) in rec.calls
    assert ("type", "hello") in rec.calls
    assert ("press", "alt") in rec.calls


def test_guest_can_move_but_not_click(isolated_home: Path) -> None:
    devices, rec = recorder_devices()
    app = make_app(isolated_home, input_devices=devices)
    with TestClient(app) as client:
        pair_new(client, app)
        guest_id, guest_token, _ = pair_new(client, app, "Guest")
        with phone(client) as p:
            p.resume(guest_id, guest_token)
            p.send("input.move", {"dx": 5, "dy": 5})
            ack = p.ack_for(p.send("input.click", {"button": "left"}))
            assert ack["error"] == "Only the owner can do that."
    assert rec.calls == [("move", 5, 5)]


def test_dropped_phone_releases_held_buttons(isolated_home: Path) -> None:
    devices, rec = recorder_devices()
    app = make_app(isolated_home, input_devices=devices)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(p.send("input.down", {"button": "left"}))["ok"]
            p.send("input.move", {"dx": 30, "dy": 0})
            p.send("ping", {"t": 1})
            p.recv_type("pong")
        # Socket closed mid-drag: the agent must release the button.
    held: set[Button] = set()
    for call in rec.calls:
        if call[0] == "press":
            held.add(call[1])
        elif call[0] == "release":
            held.discard(call[1])
    assert held == set()
    assert rec.calls[-1] == ("release", "left")


def test_unavailable_input_warns_the_owner(isolated_home: Path) -> None:
    devices = InputDevices(None, None, InputPermission(False, MAC_ACCESSIBILITY_HELP))
    app = make_app(isolated_home, input_devices=devices)
    with TestClient(app) as client:
        code = app.state.agent.pairing.current()[0]
        with phone(client) as p:
            ok = p.pair(code)
            assert ok["payload"]["features"]["input"] == {
                "available": False,
                "reason": MAC_ACCESSIBILITY_HELP,
            }
            toast = p.recv_type("toast")["payload"]
            assert toast == {"level": "warn", "message": MAC_ACCESSIBILITY_HELP}
            ack = p.ack_for(p.send("input.click", {"button": "left"}))
            assert ack["error"] == "That isn't available on this laptop yet."


def test_dry_run_never_touches_the_real_cursor(isolated_home: Path) -> None:
    devices = detect_input_devices("windows", None, dry_run=True)
    app = make_app(isolated_home, input_devices=devices)
    with TestClient(app) as client:
        device_id, token, _ = pair_new(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(p.send("input.click", {"button": "left"}))["ok"]
    assert devices.permission.available


def test_revoked_mid_drag_releases(isolated_home: Path) -> None:
    devices, rec = recorder_devices()
    app = make_app(isolated_home, input_devices=devices)
    with TestClient(app) as client:
        owner_id, owner_token, _ = pair_new(client, app)
        guest_id, guest_token, _ = pair_new(client, app, "Second")
        with phone(client) as owner, phone(client) as second:
            owner.resume(owner_id, owner_token)
            owner.ack_for(owner.send("devices.role", {"deviceId": guest_id, "role": "owner"}))
            second.resume(guest_id, guest_token)
            assert second.ack_for(second.send("input.down", {"button": "left"}))["ok"]
            owner.ack_for(owner.send("devices.revoke", {"deviceId": guest_id}))
            with pytest.raises(WebSocketDisconnect):
                for _ in range(10):
                    second.recv()
    assert rec.calls[-1] == ("release", "left")

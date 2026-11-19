from __future__ import annotations

import io
import struct
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lapremote.input.keyboard import Keyboard
from lapremote.input.mouse import Mouse
from lapremote.input.service import InputDevices, ScreenRect, absolute_point
from lapremote.preview.capture import (
    MAX_IN_FLIGHT,
    Frame,
    Monitor,
    MssGrabber,
    encode_frame,
    pack_frame,
    scaled_size,
)
from lapremote.system.permissions import InputPermission

from .test_input import Recorder
from .wsclient import Phone, make_app, pair_new, phone

MONITORS = [
    Monitor(index=0, left=0, top=0, width=1920, height=1080, primary=True),
    Monitor(index=1, left=1920, top=-200, width=2560, height=1440, primary=False),
]


class FakeGrabber:
    def __init__(self) -> None:
        self.grabs = 0

    def monitors(self) -> list[Monitor]:
        return list(MONITORS)

    def grab(self, monitor: int, width: int, quality: int) -> Frame:
        self.grabs += 1
        mon = MONITORS[monitor]
        rgb = bytes([monitor * 100, 50, 200]) * (mon.width // 40 * (mon.height // 40))
        return encode_frame(rgb, (mon.width // 40, mon.height // 40), width, quality)


def test_scaled_size() -> None:
    assert scaled_size(1920, 1080, 480) == (480, 270)
    assert scaled_size(2560, 1440, 480) == (480, 270)
    assert scaled_size(1280, 1024, 480) == (480, 384)
    assert scaled_size(320, 200, 480) == (320, 200)  # never upscale


def test_frame_header_is_big_endian() -> None:
    data = pack_frame(258, 1, b"\xff\xd8jpeg")
    assert data[:8] == b"\x00\x00\x01\x02\x00\x00\x00\x01"
    assert struct.unpack(">II", data[:8]) == (258, 1)
    assert data[8:] == b"\xff\xd8jpeg"


def test_encode_frame_scales_and_is_jpeg() -> None:
    frame = encode_frame(bytes([10, 20, 30]) * (1920 * 1080), (1920, 1080), 480, 60)
    assert frame.jpeg[:2] == b"\xff\xd8"
    assert (frame.width, frame.height) == (480, 270)
    assert Image.open(io.BytesIO(frame.jpeg)).size == (480, 270)


@pytest.mark.parametrize(
    ("rect", "x", "y", "expected"),
    [
        (ScreenRect(0, 0, 1920, 1080), 0.0, 0.0, (0, 0)),
        (ScreenRect(0, 0, 1920, 1080), 1.0, 1.0, (1919, 1079)),
        (ScreenRect(0, 0, 1920, 1080), 0.5, 0.5, (960, 540)),
        (ScreenRect(1920, -200, 2560, 1440), 0.5, 0.5, (3200, 520)),
        (ScreenRect(-1280, 0, 1280, 1024), 0.25, 0.75, (-960, 767)),
    ],
)
def test_absolute_point(rect: ScreenRect, x: float, y: float, expected: tuple[int, int]) -> None:
    assert absolute_point(rect, x, y) == expected


def owner(client: TestClient, app: object) -> tuple[str, str]:
    device_id, token, _ = pair_new(client, app)  # type: ignore[arg-type]
    return device_id, token


def frames(p: Phone, count: int) -> list[tuple[int, int, bytes]]:
    out: list[tuple[int, int, bytes]] = []
    while len(out) < count:
        message = p.ws.receive()
        data = message.get("bytes")
        if data is None:
            continue
        frame_no, monitor = struct.unpack(">II", data[:8])
        out.append((frame_no, monitor, data[8:]))
    return out


def test_preview_streams_with_backpressure(isolated_home: Path) -> None:
    grabber = FakeGrabber()
    app = make_app(isolated_home, grabber=grabber)
    with TestClient(app) as client:
        device_id, token = owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            ack, before = p.ack_with(
                p.send("preview.start", {"fps": 15, "width": 480, "monitor": 1})
            )
            assert ack["ok"] is True
            meta = next(m["payload"] for m in before if m["type"] == "preview.meta")
            assert meta["width"] == 480
            assert meta["height"] == 270
            assert [m["index"] for m in meta["monitors"]] == [0, 1]
            assert meta["monitors"][1]["left"] == 1920

            first = frames(p, MAX_IN_FLIGHT)
            assert [f[0] for f in first] == [1, 2]
            assert all(f[1] == 1 and f[2][:2] == b"\xff\xd8" for f in first)

            # Without acks the agent stops capturing at two frames in flight.
            grabs_before = grabber.grabs
            p.send("ping", {"t": 1})
            p.recv_type("pong")
            time.sleep(0.4)
            assert grabber.grabs == grabs_before

            # Acking frame 2 frees both slots: frames 3 and 4 follow.
            p.send("preview.ack", {"frame": 2})
            assert [f[0] for f in frames(p, 2)] == [3, 4]

            assert p.ack_for(p.send("preview.stop", {}))["ok"] is True


def test_preview_rejects_unknown_monitor(isolated_home: Path) -> None:
    app = make_app(isolated_home, grabber=FakeGrabber())
    with TestClient(app) as client:
        device_id, token = owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            ack = p.ack_for(p.send("preview.start", {"monitor": 5}))
            assert ack["error"] == "That screen isn't connected anymore."


def test_preview_unavailable_without_grabber(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with TestClient(app) as client:
        code = app.state.agent.pairing.current()[0]
        with phone(client) as p:
            features = p.pair(code)["payload"]["features"]
    assert features["preview"]["available"] is False


def test_absclick_maps_to_the_right_monitor(isolated_home: Path) -> None:
    rec = Recorder()
    devices = InputDevices(
        Mouse(rec, "windows"), Keyboard(rec, "windows"), InputPermission(True, None)
    )
    app = make_app(isolated_home, grabber=FakeGrabber(), input_devices=devices)
    with TestClient(app) as client:
        device_id, token = owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(
                p.send("input.absclick", {"x": 0.5, "y": 0.5, "monitor": 1, "button": "left"})
            )["ok"]
            assert p.ack_for(
                p.send("input.absclick", {"x": 0.0, "y": 1.0, "monitor": 0, "button": "right"})
            )["ok"]
            ack = p.ack_for(
                p.send("input.absclick", {"x": 0.5, "y": 0.5, "monitor": 3, "button": "left"})
            )
            assert ack["error"] == "That screen isn't connected anymore."
            ack = p.ack_for(
                p.send("input.absclick", {"x": 1.5, "y": 0.5, "monitor": 0, "button": "left"})
            )
            assert ack["ok"] is False
    assert rec.calls == [
        ("move_to", 3200, 520),
        ("press", "left"),
        ("release", "left"),
        ("move_to", 0, 1079),
        ("press", "right"),
        ("release", "right"),
    ]


def test_calibration_page(isolated_home: Path) -> None:
    with TestClient(make_app(isolated_home)) as client:
        response = client.get("/calibration")
    assert response.status_code == 200
    assert "Tap-to-click calibration" in response.text
    assert "window.__calibration" in response.text


@pytest.mark.skipif(
    sys.platform != "win32", reason="real capture is checked on the Windows dev laptop"
)
def test_real_screen_capture() -> None:
    grabber = MssGrabber()
    monitors = grabber.monitors()
    assert monitors
    frame = grabber.grab(0, 480, 60)
    assert frame.jpeg[:2] == b"\xff\xd8"
    assert frame.width == min(480, monitors[0].width)
    assert Image.open(io.BytesIO(frame.jpeg)).size == (frame.width, frame.height)

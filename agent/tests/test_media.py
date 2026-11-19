from __future__ import annotations

import asyncio
import base64
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from lapremote.input.keyboard import Keyboard
from lapremote.input.mouse import Mouse
from lapremote.input.service import InputDevices
from lapremote.media.base import (
    NoSessionBackend,
    SessionSnapshot,
    artwork_id,
    friendly_app_name,
    now_ms,
    thumbnail_jpeg,
)
from lapremote.media.linux import parse_line, read_local_art, snapshot_from_fields
from lapremote.media.macos import SESSION_ID, MacMediaBackend, snapshot_from_payload
from lapremote.media.smart_seek import (
    NO_ABSOLUTE,
    NOT_IN_FRONT,
    ApiSeek,
    KeySeek,
    SeekRefused,
    plan_seek,
)
from lapremote.system.context import ForegroundInfo, classify
from lapremote.system.permissions import InputPermission
from lapremote.system.volume import VolumeService, parse_mac, parse_pactl

from .fakes import FakeMediaBackend, FakeVolume, jpeg, session
from .test_input import Recorder
from .wsclient import Phone, make_app, pair_new, phone

YOUTUBE = ForegroundInfo("Brave", "brave.exe", "Lofi - YouTube - Brave", "browser", "youtube")
NETFLIX = ForegroundInfo("Brave", "brave.exe", "Netflix - Brave", "browser", "netflix")
GENERIC = ForegroundInfo("Brave", "brave.exe", "Some site - Brave", "browser", "generic")
WORD = ForegroundInfo("Winword", "WINWORD.EXE", "Doc", "other", None)


# ---------------------------------------------------------------- smart seek decisions


@pytest.mark.parametrize(
    ("snap", "to", "by", "fg", "expected"),
    [
        (session(position=30, duration=200), None, 10, None, ApiSeek(40)),
        (session(position=30, duration=200), None, -120, None, ApiSeek(0)),
        (session(position=195, duration=200), None, 10, None, ApiSeek(199.5)),
        (session(position=30, duration=200), 90, None, WORD, ApiSeek(90)),
        (session(can_seek=False), None, 10, YOUTUBE, KeySeek("l", 1, 10)),
        (session(can_seek=False), None, -20, YOUTUBE, KeySeek("j", 2, 10)),
        (session(can_seek=False), None, -10, NETFLIX, KeySeek("left", 1, 10)),
        (None, None, 30, NETFLIX, KeySeek("right", 3, 10)),
        (None, None, 10, GENERIC, KeySeek("right", 2, 5)),
        (None, None, -5, GENERIC, KeySeek("left", 1, 5)),
        (session(can_seek=False), None, 10, WORD, SeekRefused(NOT_IN_FRONT)),
        (session(can_seek=False), None, 10, None, SeekRefused(NOT_IN_FRONT)),
        (session(can_seek=False), 60, None, YOUTUBE, SeekRefused(NO_ABSOLUTE)),
        (None, None, 3600, YOUTUBE, KeySeek("l", 60, 10)),
    ],
)
def test_seek_plan(
    snap: SessionSnapshot | None,
    to: float | None,
    by: float | None,
    fg: ForegroundInfo | None,
    expected: object,
) -> None:
    at = snap.updated_at if snap is not None else None
    assert plan_seek(snap, to=to, by=by, foreground=fg, now_ms=at) == expected


def test_seek_plan_interpolates_playing_position() -> None:
    snap = replace(session(position=30, duration=200), updated_at=1_000_000.0)
    plan = plan_seek(snap, to=None, by=10, foreground=None, now_ms=1_005_000.0)
    assert plan == ApiSeek(45)  # 30 + 5s elapsed + 10


def test_paused_position_does_not_move() -> None:
    snap = replace(session(status="paused", position=30), updated_at=0.0)
    assert snap.position_now(1_000_000.0) == 30


# ---------------------------------------------------------------- context and helpers


@pytest.mark.parametrize(
    ("process", "title", "category", "site"),
    [
        ("brave.exe", "Stranger Things | Netflix - Brave", "browser", "netflix"),
        ("chrome.exe", "lofi beats - YouTube - Google Chrome", "browser", "youtube"),
        ("msedge.exe", "Watch | Prime Video - Edge", "browser", "prime"),
        ("brave.exe", "Spotify - Web Player - Brave", "browser", "spotify_web"),
        ("firefox.exe", "Some article", "browser", "generic"),
        ("chrome.exe", "Deck - Google Slides - Chrome", "presentation", None),
        ("Spotify.exe", "Spotify Premium", "music", None),
        ("vlc.exe", "movie.mkv - VLC media player", "video", None),
        ("POWERPNT.EXE", "Slides.pptx", "presentation", None),
        ("explorer.exe", "", "desktop", None),
        ("Code.exe", "main.py", "other", None),
    ],
)
def test_classify(process: str, title: str, category: str, site: str | None) -> None:
    info = classify(process, title)
    assert info.category == category
    assert info.site == site


@pytest.mark.parametrize(
    ("app_id", "name"),
    [
        ("SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify", "Spotify"),
        ("Brave", "Brave"),
        ("Chrome", "Chrome"),
        ("MSEdge", "Edge"),
        ("308046B0AF4A39CB", "308046B0AF4A39CB"),
        ("C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", "VLC"),
        ("Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic", "Media Player"),
        ("com.apple.Music", "Music"),
        ("org.mpris.MediaPlayer2.rhythmbox", "Rhythmbox"),
        ("", "Media"),
    ],
)
def test_friendly_app_name(app_id: str, name: str) -> None:
    assert friendly_app_name(app_id) == name


def test_thumbnail_is_small_jpeg_and_id_is_stable() -> None:
    art = jpeg(size=600)
    assert art[:2] == b"\xff\xd8"
    import io  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    assert max(Image.open(io.BytesIO(art)).size) <= 256
    assert artwork_id(art) == artwork_id(art)
    assert artwork_id(art) != artwork_id(jpeg((0, 0, 255)))
    assert len(artwork_id(art) or "") == 16
    assert artwork_id(None) is None
    assert thumbnail_jpeg(b"not an image") is None


# ---------------------------------------------------------------- macOS and Linux parsing


def test_mac_payload_to_session() -> None:
    payload = {
        "bundleIdentifier": "com.spotify.client",
        "title": "Song",
        "artist": "Band",
        "album": "LP",
        "duration": 200.5,
        "elapsedTime": 12.0,
        "timestamp": "2026-11-19T07:00:00Z",
        "playing": True,
        "playbackRate": 1,
    }
    snap = snapshot_from_payload(payload, None)
    assert snap is not None
    assert snap.id == SESSION_ID
    assert snap.app_name == "Spotify"
    assert snap.status == "playing"
    assert snap.can_seek
    assert snap.updated_at == pytest.approx(1_795_590_000_000, abs=86_400_000 * 400)
    assert snapshot_from_payload({}, None) is None


async def test_mac_stream_diff_merge_and_artwork() -> None:
    backend = MacMediaBackend("media-control")
    art = base64.b64encode(jpeg()).decode()
    full = {
        "type": "data",
        "diff": False,
        "payload": {"title": "A", "playing": True, "artworkData": art},
    }
    await backend.apply_line(__import__("json").dumps(full).encode())
    first = backend.list_sessions()[0]
    assert first.title == "A"
    assert first.artwork_id is not None
    diff = {"type": "data", "diff": True, "payload": {"playing": False}}
    await backend.apply_line(__import__("json").dumps(diff).encode())
    second = backend.list_sessions()[0]
    assert second.status == "paused"
    assert second.title == "A"
    assert second.artwork_id == first.artwork_id
    await backend.apply_line(b"not json")
    await backend.apply_line(b'{"type":"data","diff":false,"payload":{}}')
    assert backend.list_sessions() == []


def test_playerctl_line_parsing(tmp_path: Path) -> None:
    line = "\x1f".join(["spotify", "Playing", "12500000", "200000000", "Song", "Band", "LP", ""])
    fields = parse_line(line + "\n")
    assert fields is not None
    snap = snapshot_from_fields(fields, None)
    assert (snap.id, snap.status, snap.position, snap.duration) == (
        "spotify",
        "playing",
        12.5,
        200.0,
    )
    assert parse_line("too|few") is None
    art = tmp_path / "cover.png"
    art.write_bytes(b"png-bytes")
    assert read_local_art(art.as_uri()) == b"png-bytes"
    assert read_local_art("https://i.scdn.co/image/abc") is None


# ---------------------------------------------------------------- volume parsing


def test_volume_parsers() -> None:
    assert parse_mac("37,false\n") == (37, False)
    assert parse_mac("100,true") == (100, True)
    out = "Volume: front-left: 32768 /  50% / -18.06 dB,   front-right: 32768 /  50% / -18.06 dB"
    assert parse_pactl(out, "Mute: yes") == (50, True)
    assert parse_pactl(out, "Mute: no") == (50, False)


# ---------------------------------------------------------------- over the socket


def keyboard_devices() -> tuple[InputDevices, Recorder]:
    rec = Recorder()
    return (
        InputDevices(Mouse(rec, "windows"), Keyboard(rec, "windows"), InputPermission(True, None)),
        rec,
    )


def connect_owner(client: TestClient, app: Any) -> tuple[str, str]:
    device_id, token, _ = pair_new(client, app)
    return device_id, token


def media_state(p: Phone) -> dict[str, Any]:
    payload: dict[str, Any] = p.recv_type("media.state")["payload"]
    return payload


def test_media_state_on_connect_sends_artwork_once(isolated_home: Path) -> None:
    art = jpeg()
    backend = FakeMediaBackend([session("w1", art=art), session("w2", title="Other")])
    app = make_app(isolated_home, media_backend=backend)
    with TestClient(app) as client:
        device_id, token = connect_owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            state = media_state(p)
            first, second = state["sessions"]
            assert state["currentId"] == "w1"
            assert first["artworkId"] == artwork_id(art)
            assert first["artwork"].startswith("data:image/jpeg;base64,")
            assert second["artworkId"] is None
            assert second["artwork"] is None
            assert set(first) >= {"position", "duration", "rate", "updatedAt", "canSeek"}

            # A change on the same artwork: id repeated, image not re-sent.
            backend.set_sessions([session("w1", title="Next song", art=art)])
            state = media_state(p)
            assert state["sessions"][0]["title"] == "Next song"
            assert state["sessions"][0]["artworkId"] == artwork_id(art)
            assert state["sessions"][0]["artwork"] is None

            # A phone without the image asks for it.
            p.send("media.artwork", {"artworkId": artwork_id(art)})
            reply = p.recv_type("media.artwork")["payload"]
            assert reply["artwork"].startswith("data:image/jpeg;base64,")
            p.send("media.artwork", {"artworkId": "0" * 16})
            assert p.recv_type("media.artwork")["payload"] == {
                "artworkId": "0" * 16,
                "artwork": None,
            }

        # A new connection gets the image again.
        with phone(client) as p2:
            p2.resume(device_id, token)
            assert media_state(p2)["sessions"][0]["artwork"] is not None


def test_media_commands_target_sessions(isolated_home: Path) -> None:
    backend = FakeMediaBackend([session("w1"), session("w2", title="B")])
    app = make_app(isolated_home, media_backend=backend)
    with TestClient(app) as client:
        device_id, token = connect_owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(p.send("media.toggle", {}))["ok"] is True
            assert p.ack_for(p.send("media.next", {"sessionId": "w2"}))["ok"] is True
            assert p.ack_for(p.send("media.pause", {"sessionId": "gone"}))["error"] == (
                "That player isn't open anymore."
            )
            ack, before = p.ack_with(p.send("media.select", {"sessionId": "w2"}))
            assert ack["ok"] is True
            states = [m["payload"] for m in before if m["type"] == "media.state"]
            assert states[-1]["currentId"] == "w2"
            assert p.ack_for(p.send("media.play", {}))["ok"] is True
    assert backend.commands == [("w1", "toggle"), ("w2", "next"), ("w2", "play")]


def test_unresponsive_player_reports_error(isolated_home: Path) -> None:
    backend = FakeMediaBackend([session("w1"), session("w2")])
    backend.accept = False
    app = make_app(isolated_home, media_backend=backend)
    with TestClient(app) as client:
        device_id, token = connect_owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            ack = p.ack_for(p.send("media.next", {"sessionId": "w2"}))
            assert ack["error"] == "That player didn't respond."


def test_media_keys_fallback_without_sessions(isolated_home: Path) -> None:
    devices, rec = keyboard_devices()
    app = make_app(isolated_home, media_backend=NoSessionBackend(), input_devices=devices)
    with TestClient(app) as client:
        device_id, token = connect_owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert media_state(p)["sessions"] == []
            assert p.ack_for(p.send("media.toggle", {}))["ok"] is True
            assert p.ack_for(p.send("media.next", {}))["ok"] is True
    assert ("press", "media_play_pause") in rec.calls
    assert ("press", "media_next") in rec.calls


def test_api_seek(isolated_home: Path) -> None:
    backend = FakeMediaBackend([session("w1", position=100, duration=300, status="paused")])
    app = make_app(isolated_home, media_backend=backend)
    with TestClient(app) as client:
        device_id, token = connect_owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(p.send("media.seek", {"by": -120}))["ok"] is True
            assert p.ack_for(p.send("media.seek", {"to": 42.5}))["ok"] is True
    assert backend.seeks == [("w1", 0.0), ("w1", 42.5)]


def test_key_seek_goes_to_browser_only(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    devices, rec = keyboard_devices()
    backend = FakeMediaBackend([session("w1", can_seek=False, app_id="Brave")])
    app = make_app(isolated_home, media_backend=backend, input_devices=devices)
    from lapremote.media import service as media_service  # noqa: PLC0415

    with TestClient(app) as client:
        device_id, token = connect_owner(client, app)
        svc_fg: list[ForegroundInfo | None] = [YOUTUBE]
        media = next(
            h
            for h in app.state.agent.on_connect
            if getattr(h, "__self__", None) is not None
            and isinstance(h.__self__, media_service.MediaService)
        ).__self__
        monkeypatch.setattr(media, "_foreground", lambda: svc_fg[0])
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(p.send("media.seek", {"by": 20}))["ok"] is True
            svc_fg[0] = WORD
            ack = p.ack_for(p.send("media.seek", {"by": 10}))
            assert ack["error"] == NOT_IN_FRONT
    presses = [c for c in rec.calls if c[0] == "press"]
    assert presses == [("press", "l"), ("press", "l")]


async def test_position_only_updates_are_not_rebroadcast() -> None:
    from lapremote.config import Config  # noqa: PLC0415
    from lapremote.core import Agent  # noqa: PLC0415
    from lapremote.media.keys_fallback import MediaKeys  # noqa: PLC0415
    from lapremote.media.service import MediaService  # noqa: PLC0415

    agent = Agent(Config(), Path(sys.prefix) / "unused-home-never-written")
    backend = FakeMediaBackend([replace(session("w1", position=10.0), updated_at=1_000_000.0)])
    svc = MediaService(agent, backend, MediaKeys(None), lambda: None)
    calls: list[int] = []

    async def count() -> None:
        calls.append(1)

    svc.broadcast = count  # type: ignore[method-assign]
    await svc.on_change()
    assert calls == [1]
    # 5s later the app reports 15s: exactly what interpolation predicts -> no broadcast.
    backend.sessions = [replace(session("w1", position=15.0), updated_at=1_005_000.0)]
    await svc.on_change()
    assert calls == [1]
    # A user seek (drift > 1s) is broadcast.
    backend.sessions = [replace(session("w1", position=90.0), updated_at=1_006_000.0)]
    await svc.on_change()
    assert calls == [1, 1]


def test_volume_over_socket(isolated_home: Path) -> None:
    volume = FakeVolume(level=40)
    app = make_app(isolated_home, volume_backend=volume)
    with TestClient(app) as client:
        device_id, token = connect_owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.recv_type("volume.state")["payload"] == {"level": 40, "muted": False}

            def pushed(type_: str, payload: dict[str, Any]) -> dict[str, Any]:
                # The new state is pushed before the ack, so read both together.
                ack, before = p.ack_with(p.send(type_, payload))
                assert ack["ok"] is True
                states: list[dict[str, Any]] = [
                    m["payload"] for m in before if m["type"] == "volume.state"
                ]
                return states[-1]

            assert pushed("volume.set", {"level": 30}) == {"level": 30, "muted": False}
            assert pushed("volume.step", {"delta": 80})["level"] == 100
            assert pushed("volume.mute", {"muted": True}) == {"level": 100, "muted": True}
            assert p.ack_for(p.send("volume.set", {"level": 101}))["ok"] is False


async def test_volume_poll_emits_only_on_change() -> None:
    from lapremote.config import Config  # noqa: PLC0415
    from lapremote.core import Agent  # noqa: PLC0415
    from lapremote.media.keys_fallback import MediaKeys  # noqa: PLC0415

    agent = Agent(Config(), Path(sys.prefix) / "unused-home-never-written")
    sent: list[Any] = []

    async def capture(type_: str, payload: Any, where: Any = None) -> None:
        sent.append((type_, payload))

    agent.hub.broadcast = capture  # type: ignore[method-assign]
    volume = FakeVolume(level=40)
    svc = VolumeService(agent, volume, MediaKeys(None))
    await svc.refresh()
    await svc.refresh()
    volume.level = 55
    await svc.refresh()
    volume.broken = True
    await svc.refresh()
    assert [p.level for _t, p in sent] == [40, 55]


def test_volume_key_fallback(isolated_home: Path) -> None:
    devices, rec = keyboard_devices()
    app = make_app(isolated_home, input_devices=devices)
    # Replace the fake volume with "no backend" to exercise the key fallback.
    from lapremote.core import Agent  # noqa: PLC0415
    from lapremote.media.keys_fallback import MediaKeys  # noqa: PLC0415

    agent: Agent = app.state.agent
    svc = VolumeService(agent, None, MediaKeys(devices.keyboard))
    svc.register()
    with TestClient(app) as client:
        device_id, token = connect_owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(p.send("volume.step", {"delta": -6}))["ok"] is True
            assert p.ack_for(p.send("volume.set", {"level": 20}))["error"] == (
                "Setting an exact volume isn't available on this laptop."
            )
    assert [c for c in rec.calls if c == ("press", "volume_down")] == [("press", "volume_down")] * 3


@pytest.mark.skipif(sys.platform != "win32", reason="real GSMTC is Windows only")
async def test_real_windows_media_sessions_read_only() -> None:
    """Reads the real media sessions on this laptop. Never presses play or changes anything."""
    from lapremote.media.windows import WindowsMediaBackend  # noqa: PLC0415

    backend = WindowsMediaBackend()
    await backend.start()
    try:
        sessions = backend.list_sessions()
        for s in sessions:
            assert s.id.startswith("w")
            assert s.app_name
            assert s.status in ("playing", "paused", "stopped")
            assert s.updated_at > 0
            if s.artwork_jpeg is not None:
                assert s.artwork_jpeg[:2] == b"\xff\xd8"
        ids = [s.id for s in sessions]
        assert len(ids) == len(set(ids))
        # A second refresh keeps the same ids for the same sessions.
        await backend._refresh()
        assert [s.id for s in backend.list_sessions()] == ids
    finally:
        await backend.stop()
    await asyncio.sleep(0)
    _ = now_ms()

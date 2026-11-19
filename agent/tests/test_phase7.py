from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from lapremote.config import Config
from lapremote.core import Agent
from lapremote.protocol import PowerActionName, Scene
from lapremote.router import ActionError
from lapremote.scenes import SceneStore, run_steps
from lapremote.shortcuts import ShortcutStore, validate_app_target
from lapremote.storage import load_or_seed
from lapremote.system.power import PowerService
from lapremote.timer import NO_DURATION, NOTHING_PLAYING, SleepTimer, fade_levels, seconds_until_end

from .fakes import FakeBrightness, FakeLauncher, FakeMediaBackend, FakePower, FakeVolume, session
from .wsclient import Phone, make_app, pair_new, phone

# ---------------------------------------------------------------- storage and shortcuts


def test_defaults_are_seeded_once(tmp_path: Path) -> None:
    path = tmp_path / "shortcuts.json"
    data = load_or_seed(path, "shortcuts.default.json")
    assert isinstance(data, list)
    assert [s["id"] for s in data] == [
        "netflix",
        "youtube",
        "youtube-music",
        "prime-video",
        "spotify",
    ]
    path.write_text("[]", encoding="utf-8")
    assert load_or_seed(path, "shortcuts.default.json") == []


def test_broken_file_is_moved_aside(tmp_path: Path) -> None:
    path = tmp_path / "scenes.json"
    path.write_text("{oops", encoding="utf-8")
    data = load_or_seed(path, "scenes.default.json")
    assert isinstance(data, list)
    assert (tmp_path / "scenes.json.broken").read_text(encoding="utf-8") == "{oops"


def test_shortcut_store_upsert_delete_reorder(tmp_path: Path) -> None:
    store = ShortcutStore(tmp_path / "shortcuts.json")
    first = store.items()[0]
    store.upsert(first.model_copy(update={"name": "Netflix TV"}))
    assert store.items()[0].name == "Netflix TV"
    store.reorder(["spotify", "netflix"])
    assert [s.id for s in store.items()][:2] == ["spotify", "netflix"]
    assert store.delete("youtube")
    assert not store.delete("youtube")
    on_disk = json.loads((tmp_path / "shortcuts.json").read_text(encoding="utf-8"))
    assert "youtube" not in [s["id"] for s in on_disk]
    assert ShortcutStore(tmp_path / "shortcuts.json").items() == store.items()


def test_app_target_validation(tmp_path: Path) -> None:
    exe = tmp_path / "Player.exe"
    exe.write_bytes(b"MZ")
    txt = tmp_path / "notes.txt"
    txt.write_text("x", encoding="utf-8")
    assert validate_app_target("windows", str(exe)) == str(exe)
    for bad, reason in (
        ("Player.exe", "full path"),
        (str(tmp_path / "missing.exe"), "doesn't exist"),
        (str(txt), ".exe"),
        ("calc.exe && del C:\\", "full path"),
    ):
        with pytest.raises(ValueError, match=reason):
            validate_app_target("windows", bad)
    assert validate_app_target("macos", "com.spotify.client") == "com.spotify.client"
    with pytest.raises(ValueError, match=r"\.app"):
        validate_app_target("macos", str(exe))
    desktop = tmp_path / "vlc.desktop"
    desktop.write_text("[Desktop Entry]", encoding="utf-8")
    assert validate_app_target("linux", str(desktop)) == str(desktop)


def owner(client: TestClient, app: Any) -> tuple[str, str]:
    device_id, token, _ = pair_new(client, app)
    return device_id, token


def test_launcher_over_socket(isolated_home: Path, tmp_path: Path) -> None:
    launcher = FakeLauncher()
    app = make_app(isolated_home, launcher=launcher)
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ")
    with TestClient(app) as client:
        device_id, token = owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            state = p.recv_type("shortcuts.state")["payload"]["shortcuts"]
            assert state[0]["id"] == "netflix"
            assert p.ack_for(p.send("launch.open", {"shortcutId": "netflix"}))["ok"] is True
            ack = p.ack_for(p.send("launch.open", {"shortcutId": "nope"}))
            assert ack["error"] == "That shortcut doesn't exist anymore."
            app_shortcut = {"id": "game", "name": "Game", "kind": "app", "app": str(exe)}
            ack, before = p.ack_with(p.send("shortcuts.save", {"shortcut": app_shortcut}))
            assert ack["ok"] is True
            assert [m for m in before if m["type"] == "shortcuts.state"]
            assert p.ack_for(p.send("launch.open", {"shortcutId": "game"}))["ok"] is True
            bad = {"id": "bad", "name": "Bad", "kind": "app", "app": "C:\\nowhere\\x.exe"}
            assert p.ack_for(p.send("shortcuts.save", {"shortcut": bad}))["error"] == (
                "That app path doesn't exist on this laptop."
            )
            launcher.fail = True
            assert (
                p.ack_for(p.send("launch.open", {"shortcutId": "youtube"}))["error"]
                == "Couldn't open YouTube."
            )
    assert launcher.urls == ["https://www.netflix.com/browse"]
    assert launcher.apps == [str(exe)]


def test_guest_cannot_edit_or_launch(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with TestClient(app) as client:
        owner(client, app)
        guest_id, guest_token, _ = pair_new(client, app, "Guest")
        with phone(client) as p:
            p.resume(guest_id, guest_token)
            for type_, payload in (
                ("launch.open", {"shortcutId": "netflix"}),
                ("shortcuts.delete", {"shortcutId": "netflix"}),
                ("scene.run", {"sceneId": "movie-night"}),
                ("timer.set", {"mode": "minutes", "minutes": 5, "then": "pause"}),
                ("power.prepare", {"action": "lock"}),
                ("brightness.set", {"level": 10}),
            ):
                assert (
                    p.ack_for(p.send(type_, payload))["error"] == "Only the owner can do that."
                ), type_


# ---------------------------------------------------------------- scenes


class FakeActions:
    def __init__(self, media: FakeMediaBackend | None = None, volume: int | None = 50) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.media = SimpleNamespace(backend=media or FakeMediaBackend())
        self.volume = volume
        self.fail_on: set[str] = set()

    def _do(self, name: str, value: Any = None) -> None:
        self.calls.append((name, value))
        if name in self.fail_on:
            raise ActionError(f"{name} failed")

    def volume_level(self) -> int | None:
        return self.volume

    async def volume_set(self, level: int) -> None:
        self._do("volume", level)
        self.volume = level

    async def brightness_set(self, level: int) -> None:
        self._do("brightness", level)

    async def launch(self, shortcut_id: str) -> None:
        self._do("launch", shortcut_id)

    async def media_command(self, action: str, session_id: str | None = None) -> None:
        self._do("media", action)

    async def pause_all(self) -> int:
        self._do("pause_all")
        return 1

    async def power_run(self, action: PowerActionName) -> None:
        self._do("power", action)


async def no_wait(_seconds: float) -> None:
    await asyncio.sleep(0)


async def test_scene_steps_run_in_order_and_survive_failures() -> None:
    scene = Scene.model_validate(
        {
            "id": "s",
            "name": "S",
            "steps": [
                {"type": "volume.set", "level": 40},
                {"type": "brightness.set", "level": 60},
                {"type": "wait", "ms": 1500},
                {"type": "launch.open", "shortcutId": "netflix"},
                {"type": "media.play"},
                {"type": "media.pause"},
            ],
        }
    )
    actions = FakeActions()
    actions.fail_on = {"brightness"}
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    results = await run_steps(scene.steps, actions, sleep)  # type: ignore[arg-type]
    assert [c[0] for c in actions.calls] == ["volume", "brightness", "launch", "media", "pause_all"]
    assert slept == [1.5]
    assert [(r.type, r.ok) for r in results] == [
        ("volume.set", True),
        ("brightness.set", False),
        ("wait", True),
        ("launch.open", True),
        ("media.play", True),
        ("media.pause", True),
    ]
    assert results[1].error == "brightness failed"


def test_default_scenes(tmp_path: Path) -> None:
    store = SceneStore(tmp_path / "scenes.json")
    movie = store.get("movie-night")
    assert movie is not None
    assert [s.type for s in movie.steps] == ["volume.set", "brightness.set", "launch.open"]
    assert store.get("focus-music") is not None


def test_scene_over_socket(isolated_home: Path) -> None:
    launcher = FakeLauncher()
    volume = FakeVolume(level=80)
    brightness = FakeBrightness(level=90)
    app = make_app(
        isolated_home, launcher=launcher, volume_backend=volume, brightness_backend=brightness
    )
    with TestClient(app) as client:
        device_id, token = owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            assert p.ack_for(p.send("scene.run", {"sceneId": "movie-night"}))["ok"] is True
            toast = p.recv_type("toast", limit=40)["payload"]
            assert toast == {"level": "success", "message": "Movie Night is on."}
            assert p.ack_for(p.send("scenes.delete", {"sceneId": "focus-music"}))["ok"] is True
            assert p.ack_for(p.send("scene.run", {"sceneId": "focus-music"}))["error"] == (
                "That scene doesn't exist anymore."
            )
    assert volume.level == 40
    assert brightness.level == 60
    assert launcher.urls == ["https://www.netflix.com/browse"]


# ---------------------------------------------------------------- timer


def test_seconds_until_end() -> None:
    playing = replace(session(position=100, duration=250), updated_at=1_000_000.0)
    assert seconds_until_end(playing, 1_010_000.0) == pytest.approx(140)
    paused = replace(playing, status="paused")
    assert seconds_until_end(paused, 9_999_999.0) == pytest.approx(150)
    fast = replace(playing, rate=2.0)
    assert seconds_until_end(fast, 1_000_000.0) == pytest.approx(75)
    with pytest.raises(ActionError, match=NO_DURATION):
        seconds_until_end(replace(playing, duration=None), 1_000_000.0)
    with pytest.raises(ActionError, match=NOTHING_PLAYING):
        seconds_until_end(None, 1_000_000.0)


def test_fade_levels() -> None:
    assert fade_levels(30, 30) == list(range(29, -1, -1))
    assert fade_levels(80, 4) == [60, 40, 20, 0]
    assert fade_levels(50, 0.4) == [0]


def timer_with(actions: FakeActions, fade: float = 3) -> tuple[SleepTimer, Agent]:
    agent = Agent(Config(), Path(sys.prefix) / "unused-home-never-written")
    timer = SleepTimer(agent, actions, fade_seconds=fade, sleep=no_wait)  # type: ignore[arg-type]
    return timer, agent


async def test_timer_fades_pauses_restores_and_locks() -> None:
    actions = FakeActions(volume=60)
    timer, _agent = timer_with(actions)
    state = await timer.start("minutes", "pause_lock", 0.1)
    assert state.active
    assert state.ends_at is not None
    for _ in range(50):
        await asyncio.sleep(0)
    assert actions.calls == [
        ("volume", 40),
        ("volume", 20),
        ("volume", 0),
        ("pause_all", None),
        ("volume", 60),
        ("power", "lock"),
    ]
    assert not timer.state().active


async def test_timer_cancel_mid_fade_restores_volume() -> None:
    actions = FakeActions(volume=50)
    started = asyncio.Event()
    release = asyncio.Event()

    async def sleep(seconds: float) -> None:
        if actions.calls:
            started.set()
            await release.wait()

    agent = Agent(Config(), Path(sys.prefix) / "unused-home-never-written")
    timer = SleepTimer(agent, actions, fade_seconds=5, sleep=sleep)  # type: ignore[arg-type]
    await timer.start("minutes", "pause_sleep", 1)
    await asyncio.wait_for(started.wait(), 2)
    await timer.cancel()
    assert actions.calls[-1] == ("volume", 50)
    assert ("pause_all", None) not in actions.calls
    assert ("power", "sleep") not in actions.calls
    assert not timer.state().active


async def test_timer_end_of_media_uses_the_current_session() -> None:
    media = FakeMediaBackend(
        [replace(session(position=10, duration=20, status="paused"), updated_at=0)]
    )
    actions = FakeActions(media=media)
    timer, _ = timer_with(actions, fade=0)
    state = await timer.start("end_of_media", "pause", None)
    assert state.mode == "end_of_media"
    assert state.ends_at is not None
    with pytest.raises(ActionError, match=NOTHING_PLAYING):
        await timer_with(FakeActions())[0].start("end_of_media", "pause", None)
    await timer.cancel()


def test_timer_over_socket(isolated_home: Path) -> None:
    volume = FakeVolume(level=30)
    media = FakeMediaBackend([session("w1", status="playing")])
    power = FakePower()
    app = make_app(isolated_home, volume_backend=volume, media_backend=media, power_backend=power)
    with TestClient(app) as client:
        device_id, token = owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            ack, before = p.ack_with(
                p.send("timer.set", {"mode": "minutes", "minutes": 0.005, "then": "pause_sleep"})
            )
            assert ack["ok"] is True
            started = [m["payload"] for m in before if m["type"] == "timer.state"][-1]
            assert started["active"] is True
            assert started["then"] == "pause_sleep"
            finished = p.recv_type("timer.state", limit=60)["payload"]
            assert finished["active"] is False
            assert p.recv_type("toast", limit=20)["payload"]["message"] == "Sleep timer: paused."
            ack = p.ack_for(p.send("timer.set", {"mode": "end_of_media", "then": "pause"}))
            assert ack["ok"] is True
            assert p.ack_for(p.send("timer.cancel", {}))["ok"] is True
    assert ("w1", "pause") in media.commands
    assert power.actions == ["sleep"]
    assert volume.level == 30


# ---------------------------------------------------------------- power


def test_power_tokens_expire_are_single_use_and_bound_to_the_action() -> None:
    now = [100.0]
    service = PowerService(
        Agent(Config(), Path(sys.prefix) / "unused-home-never-written"),
        FakePower(),
        clock=lambda: now[0],
        wall=lambda: 1_000.0,
    )
    token = service.issue("shutdown")
    assert token.expires_at == pytest.approx(1_010_000.0)
    with pytest.raises(ActionError, match="different action"):
        service.redeem("restart", token.confirm_token)
    token = service.issue("lock")
    service.redeem("lock", token.confirm_token)
    with pytest.raises(ActionError, match="expired"):
        service.redeem("lock", token.confirm_token)
    token = service.issue("sleep")
    now[0] += 10.01
    with pytest.raises(ActionError, match="expired"):
        service.redeem("sleep", token.confirm_token)
    with pytest.raises(ActionError, match="expired"):
        service.redeem("sleep", "made-up-token")


def power_flow(p: Phone, action: str) -> str:
    p.send("power.prepare", {"action": action})
    token: str = p.recv_type("power.token")["payload"]["confirmToken"]
    return token


def test_power_over_socket(isolated_home: Path) -> None:
    power = FakePower()
    app = make_app(isolated_home, power_backend=power)
    with TestClient(app) as client:
        device_id, token = owner(client, app)
        with phone(client) as p:
            p.resume(device_id, token)
            confirm = power_flow(p, "lock")
            assert (
                p.ack_for(p.send("power.action", {"action": "lock", "confirmToken": confirm}))["ok"]
                is True
            )
            replay = p.ack_for(p.send("power.action", {"action": "lock", "confirmToken": confirm}))
            assert replay["error"] == "That confirmation expired. Hold the button again."
            confirm = power_flow(p, "restart")
            wrong = p.ack_for(
                p.send("power.action", {"action": "shutdown", "confirmToken": confirm})
            )
            assert wrong["ok"] is False
    assert power.actions == ["lock"]


# ---------------------------------------------------------------- brightness


def test_brightness_over_socket(isolated_home: Path) -> None:
    brightness = FakeBrightness(level=70)
    app = make_app(isolated_home, brightness_backend=brightness)
    with TestClient(app) as client:
        device_id, token = owner(client, app)
        with phone(client) as p:
            ok = p.resume(device_id, token)
            assert ok["payload"]["features"]["brightness"]["available"] is True
            assert p.recv_type("brightness.state")["payload"] == {"level": 70, "supported": True}
            ack, before = p.ack_with(p.send("brightness.set", {"level": 35}))
            assert ack["ok"] is True
            assert [m["payload"] for m in before if m["type"] == "brightness.state"][-1][
                "level"
            ] == 35


def test_brightness_unavailable(isolated_home: Path) -> None:
    app = make_app(isolated_home)
    with TestClient(app) as client:
        device_id, token = owner(client, app)
        with phone(client) as p:
            ok = p.resume(device_id, token)
            assert ok["payload"]["features"]["brightness"]["available"] is False
            assert p.recv_type("brightness.state")["payload"] == {"level": None, "supported": False}


@pytest.mark.skipif(
    sys.platform != "win32", reason="real brightness is read on the Windows dev laptop"
)
def test_real_brightness_read_only() -> None:
    from lapremote.system.brightness import create_brightness_backend  # noqa: PLC0415

    backend, reason = create_brightness_backend("windows")
    assert backend is not None, reason
    assert 0 <= backend.get() <= 100

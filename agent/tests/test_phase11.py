"""Phase 11: volume indicator on the laptop, and the features added after v1.0.0."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from lapremote.config import Config
from lapremote.core import Agent
from lapremote.input.keyboard import Keyboard
from lapremote.media.keys_fallback import MediaKeys
from lapremote.system.volume import VolumeService

from .fakes import FakeVolume
from .test_input import Recorder

# ---------------------------------------------------------------- volume indicator


def make_volume(
    tmp_path: Path, level: int = 40, muted: bool = False
) -> tuple[VolumeService, FakeVolume, Recorder]:
    rec = Recorder()
    keys = MediaKeys(Keyboard(rec, "windows"))
    backend = FakeVolume(level=level, muted=muted)
    agent = Agent(Config(), tmp_path)
    service = VolumeService(
        agent, backend, keys, show_osd=True, osd_delay=0.05, key_wait=0.02, key_settle=0.01
    )
    return service, backend, rec


def pressed(rec: Recorder) -> list[object]:
    return [call[1] for call in rec.calls if call[0] == "press"]


class DelayedKeysVolume(FakeVolume):
    """Like Windows: a volume key press changes the level by 2, but only a little later."""

    def __init__(self, level: int, delay: float) -> None:
        super().__init__(level=level)
        self.delay = delay
        self.pending: list[tuple[float, int]] = []

    def key(self, name: str) -> None:
        step = {"volume_up": 2, "volume_down": -2}.get(name)
        if step is not None:
            self.pending.append((time.monotonic() + self.delay, step))

    async def get(self) -> tuple[int, bool]:
        now = time.monotonic()
        for _due, step in [p for p in self.pending if p[0] <= now]:
            self.level = max(0, min(100, self.level + step))
        self.pending = [p for p in self.pending if p[0] > now]
        return await super().get()


class KeysInto:
    """Keyboard backend that sends volume keys into a DelayedKeysVolume."""

    def __init__(self, volume: DelayedKeysVolume) -> None:
        self.volume = volume
        self.presses: list[str] = []

    def press(self, key: object) -> None:
        self.presses.append(str(key))
        self.volume.key(str(key))

    def release(self, key: object) -> None:
        return None

    def type(self, text: str) -> None:
        return None

    def resolve(self, name: str) -> object:
        return name


@pytest.mark.parametrize("level", [0, 40, 99, 100])
def test_late_key_presses_never_leave_the_volume_changed(tmp_path: Path, level: int) -> None:
    # The real laptop applied the second key press after the level was put back, which left
    # the volume 2 lower. The indicator must wait for each press to land.
    backend = DelayedKeysVolume(level=level, delay=0.08)
    keys = KeysInto(backend)
    service = VolumeService(
        Agent(Config(), tmp_path),
        backend,
        MediaKeys(Keyboard(keys, "windows")),
        show_osd=True,
        key_wait=0.5,
        key_settle=0.1,
    )

    async def run() -> int:
        await service.show_indicator()
        await asyncio.sleep(0.3)  # anything still in flight lands now
        return (await backend.get())[0]

    assert asyncio.run(run()) == level
    assert len(keys.presses) == 2


def test_indicator_taps_up_then_down(tmp_path: Path) -> None:
    service, backend, rec = make_volume(tmp_path, level=40)
    asyncio.run(service.show_indicator())
    assert pressed(rec) == ["volume_up", "volume_down"]
    assert backend.level == 40


def test_indicator_goes_down_first_at_the_top(tmp_path: Path) -> None:
    service, _backend, rec = make_volume(tmp_path, level=100)
    asyncio.run(service.show_indicator())
    assert pressed(rec) == ["volume_down", "volume_up"]


def test_no_indicator_while_muted(tmp_path: Path) -> None:
    service, backend, rec = make_volume(tmp_path, level=40, muted=True)
    asyncio.run(service.show_indicator())
    assert pressed(rec) == []
    assert backend.muted is True


def test_slider_moves_show_the_indicator_once_after_the_last_change(tmp_path: Path) -> None:
    service, backend, rec = make_volume(tmp_path, level=40)

    async def drag() -> None:
        for level in (42, 45, 50, 55, 60):
            await service.set_level(level, show=True)
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.2)

    asyncio.run(drag())
    assert pressed(rec) == ["volume_up", "volume_down"]
    assert backend.level == 60
    assert backend.sets[-1] == 60


def test_quiet_changes_never_show_the_indicator(tmp_path: Path) -> None:
    service, backend, rec = make_volume(tmp_path, level=40)

    async def fade() -> None:
        # The sleep timer's fade and scenes set the level without show=True.
        for level in (38, 30, 20):
            await service.set_level(level)
        await asyncio.sleep(0.2)

    asyncio.run(fade())
    assert pressed(rec) == []
    assert backend.level == 20


def test_indicator_off_when_not_enabled(tmp_path: Path) -> None:
    rec = Recorder()
    backend = FakeVolume(level=40)
    service = VolumeService(Agent(Config(), tmp_path), backend, MediaKeys(Keyboard(rec, "windows")))

    async def change() -> None:
        await service.set_level(70, show=True)
        await asyncio.sleep(0.5)

    asyncio.run(change())
    assert pressed(rec) == []


class KeyMuteVolume(FakeVolume):
    """Mute state follows the mute key, as on a real laptop."""

    def __init__(self, rec: Recorder, level: int = 40) -> None:
        super().__init__(level=level)
        self.rec = rec

    async def get(self) -> tuple[int, bool]:
        presses = sum(1 for call in self.rec.calls if call == ("press", "volume_mute"))
        self.muted = presses % 2 == 1
        return await super().get()


def test_mute_uses_the_mute_key_so_the_indicator_shows(tmp_path: Path) -> None:
    rec = Recorder()
    backend = KeyMuteVolume(rec)
    service = VolumeService(
        Agent(Config(), tmp_path), backend, MediaKeys(Keyboard(rec, "windows")), show_osd=True
    )
    asyncio.run(service.set_muted(True))
    assert pressed(rec) == ["volume_mute"]
    assert service.state == (40, True)
    # Already muted: no second press.
    asyncio.run(service.set_muted(True))
    assert pressed(rec) == ["volume_mute"]


def test_mute_falls_back_to_the_audio_api_when_the_key_does_nothing(tmp_path: Path) -> None:
    service, backend, rec = make_volume(tmp_path, level=40)
    asyncio.run(service.set_muted(True))
    assert pressed(rec) == ["volume_mute"]
    assert backend.muted is True


@pytest.mark.parametrize("level", [0, 1, 50, 98, 99, 100])
def test_indicator_never_changes_the_level(tmp_path: Path, level: int) -> None:
    service, backend, _rec = make_volume(tmp_path, level=level)
    asyncio.run(service.show_indicator())
    assert backend.level == level

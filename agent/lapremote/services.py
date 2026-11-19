"""Builds every feature service for an agent. Tests pass fakes through `Overrides`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import httpx

from lapremote.actions import Actions
from lapremote.ai.planner import Planner
from lapremote.ai.providers import ChatProvider, create_provider
from lapremote.ai.service import AiService
from lapremote.core import Agent
from lapremote.input.service import (
    InputDevices,
    InputService,
    ScreenRect,
    detect_input_devices,
    register_input,
)
from lapremote.media.base import MediaBackend
from lapremote.media.keys_fallback import MediaKeys
from lapremote.media.service import MediaService, create_media_backend
from lapremote.preview.capture import Grabber, PreviewService, create_grabber
from lapremote.scenes import SceneService, SceneStore
from lapremote.shortcuts import Launcher, ShortcutService, ShortcutStore, create_launcher
from lapremote.system.brightness import (
    BrightnessBackend,
    BrightnessService,
    create_brightness_backend,
)
from lapremote.system.context import ContextService, ForegroundReader, make_reader
from lapremote.system.platform_info import detect_display_server
from lapremote.system.power import PowerBackend, PowerService, create_power_backend
from lapremote.system.volume import VolumeBackend, VolumeService, create_volume_backend
from lapremote.timer import SleepTimer

INPUT_DRY_RUN_ENV = "LAPREMOTE_INPUT_DRY_RUN"
Auto = Literal["auto"]


@dataclass
class Overrides:
    """`None` for an injected backend means "not available"; "auto" means detect the real one."""

    input_devices: InputDevices | None = None
    media_backend: MediaBackend | None = None
    volume_backend: VolumeBackend | Auto | None = "auto"
    foreground_reader: ForegroundReader | Auto | None = "auto"
    grabber: Grabber | Auto | None = "auto"
    brightness_backend: BrightnessBackend | Auto | None = "auto"
    power_backend: PowerBackend | Auto = "auto"
    launcher: Launcher | Auto = "auto"
    ai_provider: ChatProvider | Auto | None = "auto"


@dataclass
class Services:
    media: MediaService
    volume: VolumeService
    brightness: BrightnessService
    shortcuts: ShortcutService
    scenes: SceneService
    timer: SleepTimer
    power: PowerService
    preview: PreviewService
    actions: Actions
    input: InputService
    input_available: bool
    context: ContextService
    ai: AiService | None


def build_services(agent: Agent, ov: Overrides) -> Services:
    os_name = agent.os
    devices = ov.input_devices or detect_input_devices(
        os_name,
        detect_display_server(os_name),
        dry_run=os.environ.get(INPUT_DRY_RUN_ENV) == "1",
    )

    preview = PreviewService(agent, create_grabber() if ov.grabber == "auto" else ov.grabber)
    preview.register()

    async def monitor_rects() -> list[ScreenRect]:
        return [ScreenRect(m.left, m.top, m.width, m.height) for m in await preview.monitors()]

    input_service = register_input(
        agent, devices, monitor_rects if ov.grabber is not None else None
    )

    keys = MediaKeys(devices.keyboard)
    hint: str | None = None
    media_backend = ov.media_backend
    if media_backend is None:
        media_backend, hint = create_media_backend(os_name)
    reader = make_reader() if ov.foreground_reader == "auto" else ov.foreground_reader
    media = MediaService(agent, media_backend, keys, reader or (lambda: None), hint)
    media.register()
    context = ContextService(agent, reader)
    context.register()

    volume = VolumeService(
        agent,
        create_volume_backend(os_name) if ov.volume_backend == "auto" else ov.volume_backend,
        keys,
    )
    volume.register()

    if ov.brightness_backend == "auto":
        brightness_backend, reason = create_brightness_backend(os_name)
    else:
        brightness_backend = ov.brightness_backend
        reason = None if brightness_backend is not None else "Brightness control isn't available."
    brightness = BrightnessService(agent, brightness_backend, reason)
    brightness.register()

    launcher = (
        create_launcher(os_name, agent.config.preferred_browser)
        if ov.launcher == "auto"
        else ov.launcher
    )
    shortcuts = ShortcutService(agent, ShortcutStore(agent.data_dir / "shortcuts.json"), launcher)
    shortcuts.register()

    power = PowerService(
        agent, create_power_backend(os_name) if ov.power_backend == "auto" else ov.power_backend
    )
    power.register()

    actions = Actions(media, volume, brightness, shortcuts, power)
    scenes = SceneService(agent, SceneStore(agent.data_dir / "scenes.json"), actions)
    scenes.register()
    timer = SleepTimer(agent, actions)
    timer.register()

    services = Services(
        media=media,
        volume=volume,
        brightness=brightness,
        shortcuts=shortcuts,
        scenes=scenes,
        timer=timer,
        power=power,
        preview=preview,
        actions=actions,
        input=input_service,
        input_available=devices.permission.available,
        context=context,
        ai=None,
    )
    services.ai = _build_ai(agent, services, ov.ai_provider)
    return services


def _build_ai(
    agent: Agent, services: Services, provider: ChatProvider | Auto | None
) -> AiService | None:
    if provider is None:
        agent.set_feature("ai", False, "The AI assistant is turned off.")
        return None
    if provider == "auto":
        client = httpx.AsyncClient()

        async def close_client() -> None:
            await client.aclose()

        agent.on_shutdown.append(close_client)
        provider = create_provider(agent.config.ai, client)
    service = AiService(agent, services, Planner(provider), services.context)
    service.register()
    return service

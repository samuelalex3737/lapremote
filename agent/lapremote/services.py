"""Builds every feature service for an agent. Tests pass fakes through `Overrides`."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx

from lapremote.actions import Actions
from lapremote.ai.planner import Planner
from lapremote.ai.providers import ChatProvider, create_provider
from lapremote.ai.service import AiService
from lapremote.apps import AppSource, AppsService, create_app_source
from lapremote.clipboard import ClipboardBackend, ClipboardService, create_clipboard
from lapremote.core import Agent
from lapremote.input.service import (
    InputDevices,
    InputService,
    ScreenRect,
    detect_input_devices,
    register_input,
)
from lapremote.layouts import LayoutService, LayoutStore
from lapremote.media.base import MediaBackend
from lapremote.media.keys_fallback import MediaKeys
from lapremote.media.service import MediaService, create_media_backend
from lapremote.peers import PeerService, agent_id, send_magic_packet
from lapremote.preview.capture import Grabber, PreviewService, create_grabber
from lapremote.scenes import SceneService, SceneStore
from lapremote.shortcuts import (
    IconFetcher,
    Launcher,
    ShortcutService,
    ShortcutStore,
    create_launcher,
)
from lapremote.site_icons import fetch_site_icon
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
    app_source: AppSource | Auto = "auto"
    clipboard: ClipboardBackend | Auto | None = "auto"
    # Fetches a website's icon; None turns site icons off (tests never go online).
    site_icon: IconFetcher | Auto | None = "auto"
    wol_sender: Callable[[str, list[str]], None] | Auto = "auto"


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
    apps: AppsService
    clipboard: ClipboardService
    layouts: LayoutService
    peers: PeerService


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
        # Windows only shows its volume indicator for volume keys; see show_indicator.
        show_osd=os_name == "windows",
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
    apps = AppsService(
        agent, create_app_source(os_name) if ov.app_source == "auto" else ov.app_source
    )
    apps.register()
    shortcuts = ShortcutService(
        agent,
        ShortcutStore(agent.data_dir / "shortcuts.json"),
        launcher,
        apps,
        _site_icon_fetcher(agent, ov.site_icon),
    )
    shortcuts.register()
    clipboard = ClipboardService(
        agent, create_clipboard(os_name) if ov.clipboard == "auto" else ov.clipboard, launcher
    )
    clipboard.register()
    layouts = LayoutService(agent, LayoutStore(agent.data_dir / "layouts.json", os_name))
    layouts.register()
    peers = PeerService(
        agent,
        agent_id(agent.data_dir),
        sender=send_magic_packet if ov.wol_sender == "auto" else ov.wol_sender,
    )
    peers.register()

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
        apps=apps,
        clipboard=clipboard,
        layouts=layouts,
        peers=peers,
    )
    services.ai = _build_ai(agent, services, ov.ai_provider)
    return services


def _site_icon_fetcher(agent: Agent, choice: IconFetcher | Auto | None) -> IconFetcher | None:
    if choice != "auto":
        return choice
    client = httpx.AsyncClient()

    async def close_client() -> None:
        await client.aclose()

    agent.on_shutdown.append(close_client)

    async def fetch(url: str) -> str | None:
        return await fetch_site_icon(url, client)

    return fetch


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

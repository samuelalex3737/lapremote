"""One place for actions that scenes, the sleep timer and the AI planner run.

Every method goes through the same services the phone uses, so the same checks
and allowlists apply no matter who triggers an action.
"""

from __future__ import annotations

from lapremote.media.base import MediaCommand, NoSessionBackend
from lapremote.media.service import MediaService
from lapremote.protocol import PowerActionName
from lapremote.router import ActionError
from lapremote.shortcuts import ShortcutService
from lapremote.system.brightness import BrightnessService
from lapremote.system.power import PowerService
from lapremote.system.volume import VolumeService


class Actions:
    def __init__(
        self,
        media: MediaService,
        volume: VolumeService,
        brightness: BrightnessService,
        shortcuts: ShortcutService,
        power: PowerService,
    ) -> None:
        self.media = media
        self.volume = volume
        self.brightness = brightness
        self.shortcuts = shortcuts
        self.power = power

    def volume_level(self) -> int | None:
        state = self.volume.state
        return state[0] if state is not None else None

    async def volume_set(self, level: int) -> None:
        await self.volume.set_level(level)

    async def brightness_set(self, level: int) -> None:
        await self.brightness.set_level(level)

    async def launch(self, shortcut_id: str) -> None:
        await self.shortcuts.launch(shortcut_id)

    async def media_command(self, action: MediaCommand, session_id: str | None = None) -> None:
        await self.media.command(action, session_id)

    def playing_ids(self) -> list[str]:
        return [s.id for s in self.media.backend.list_sessions() if s.status == "playing"]

    async def pause_all(self) -> int:
        """Pause every playing session. Returns how many were paused."""
        playing = self.playing_ids()
        for session_id in playing:
            await self.media.command("pause", session_id)
        if not playing and isinstance(self.media.backend, NoSessionBackend):
            # Without a session API the play/pause key is the only option.
            try:
                await self.media.command("pause")
            except ActionError:
                return 0
            return 1
        return len(playing)

    async def power_run(self, action: PowerActionName) -> None:
        await self.power.run(action)

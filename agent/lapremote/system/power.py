"""Lock, sleep, restart and shut down, behind a server-issued confirm token.

The phone asks for a token (power.prepare), shows hold-to-confirm, then sends
power.action with the token. A token is single use, bound to its action and
valid for 10 seconds, so a replayed or forged message can't power the laptop off.
"""

from __future__ import annotations

import ctypes
import secrets
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import OsName, PowerAction, PowerActionName, PowerPrepare, PowerToken
from lapremote.router import ActionError

log = get_logger("power")

TOKEN_TTL_SECONDS = 10.0


class PowerError(Exception):
    """The power action could not be started."""


class PowerBackend(Protocol):
    def run(self, action: PowerActionName) -> None: ...


def _run(args: list[str]) -> None:
    try:
        result = subprocess.run(  # noqa: S603 - fixed executables and arguments only
            args, capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PowerError(str(exc)) from exc
    if result.returncode != 0:
        msg = f"{args[0]} exited with {result.returncode}"
        raise PowerError(msg)


class WindowsPower:
    def run(self, action: PowerActionName) -> None:
        windll = ctypes.windll  # type: ignore[attr-defined,unused-ignore]
        if action == "lock":
            if not windll.user32.LockWorkStation():
                msg = "LockWorkStation failed"
                raise PowerError(msg)
            return
        if action == "sleep":
            # SetSuspendState(hibernate=False, force=False, disableWakeEvents=False).
            # With hibernation enabled in Windows, this hibernates instead.
            if not windll.powrprof.SetSuspendState(0, 0, 0):
                msg = "SetSuspendState failed"
                raise PowerError(msg)
            return
        exe = shutil.which("shutdown")
        if exe is None:
            msg = "shutdown.exe not found"
            raise PowerError(msg)
        _run([exe, "/r" if action == "restart" else "/s", "/t", "0"])


class MacPower:
    def run(self, action: PowerActionName) -> None:
        if action == "lock":
            _run(["/usr/bin/pmset", "displaysleepnow"])
        elif action == "sleep":
            _run(["/usr/bin/pmset", "sleepnow"])
        else:
            verb = "restart" if action == "restart" else "shut down"
            _run(["/usr/bin/osascript", "-e", f'tell application "System Events" to {verb}'])


class LinuxPower:
    def run(self, action: PowerActionName) -> None:
        if action == "lock":
            exe = shutil.which("loginctl")
            args = ["lock-session"]
        else:
            exe = shutil.which("systemctl")
            args = [{"sleep": "suspend", "restart": "reboot", "shutdown": "poweroff"}[action]]
        if exe is None:
            msg = "loginctl/systemctl not found"
            raise PowerError(msg)
        _run([exe, *args])


def create_power_backend(os_name: OsName) -> PowerBackend:
    if os_name == "windows":
        return WindowsPower()
    if os_name == "macos":
        return MacPower()
    return LinuxPower()


@dataclass
class _Token:
    action: PowerActionName
    expires: float


Clock = Callable[[], float]


class PowerService:
    def __init__(
        self,
        agent: Agent,
        backend: PowerBackend,
        clock: Clock = time.monotonic,
        wall: Clock = time.time,
    ) -> None:
        self._agent = agent
        self._backend = backend
        self._clock = clock
        self._wall = wall
        self._tokens: dict[str, _Token] = {}

    def register(self) -> None:
        self._agent.set_feature("power", True)
        self._agent.router.register("power.prepare", self._prepare)
        self._agent.router.register("power.action", self._action)

    def issue(self, action: PowerActionName) -> PowerToken:
        now = self._clock()
        self._tokens = {k: v for k, v in self._tokens.items() if v.expires > now}
        token = secrets.token_urlsafe(24)
        self._tokens[token] = _Token(action, now + TOKEN_TTL_SECONDS)
        return PowerToken(
            action=action,
            confirm_token=token,
            expires_at=(self._wall() + TOKEN_TTL_SECONDS) * 1000,
        )

    def redeem(self, action: PowerActionName, token: str) -> None:
        entry = self._tokens.pop(token, None)
        if entry is None or entry.expires <= self._clock():
            raise ActionError("That confirmation expired. Hold the button again.")
        if entry.action != action:
            raise ActionError("That confirmation was for a different action.")

    async def run(self, action: PowerActionName) -> None:
        """Run an action that was already confirmed (or comes from the sleep timer)."""
        log_event(log, "power_action", action=action)
        try:
            self._backend.run(action)
        except PowerError as exc:
            log_event(log, "power_failed", level=40, action=action, error=str(exc))
            raise ActionError(
                f"Couldn't {action.replace('shutdown', 'shut down')} the laptop."
            ) from exc

    async def _prepare(self, conn: Connection, p: PowerPrepare) -> None:
        await conn.send("power.token", self.issue(p.action))

    async def _action(self, _conn: Connection, p: PowerAction) -> None:
        self.redeem(p.action, p.confirm_token)
        await self.run(p.action)

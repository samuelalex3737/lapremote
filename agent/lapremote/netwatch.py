"""Notice when the laptop's Wi-Fi address changes.

Phones reach the laptop by its address, and a browser keeps each address's pairing
separately, so after a change (another Wi-Fi, a new address from the router) phones
must scan a fresh code. The last address is remembered across restarts, so a change
is noticed both while LapRemote runs and when it starts on a new network.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lapremote.logging_setup import get_logger, log_event
from lapremote.storage import write_json_atomic

NETWORK_FILE = "network.json"
CHECK_SECONDS = 10.0

log = get_logger("network")


@dataclass(frozen=True)
class Move:
    previous: str
    current: str


MoveListener = Callable[[Move], Awaitable[None] | None]
AddressListener = Callable[[str], Awaitable[None] | None]


class AddressMemory:
    """The laptop's last Wi-Fi address, in ~/.lapremote/network.json."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def last(self) -> str | None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        ip = data.get("lanIp") if isinstance(data, dict) else None
        return ip if isinstance(ip, str) and ip else None

    def record(self, ip: str) -> Move | None:
        """Remember `ip`. Returns the move when it differs from the remembered address."""
        previous = self.last()
        if previous == ip:
            return None
        try:
            write_json_atomic(self._path, {"lanIp": ip})
        except OSError as exc:
            log_event(log, "network_memory_failed", level=logging.WARNING, error=str(exc))
        return Move(previous, ip) if previous is not None else None


class NetworkWatch:
    """The current Wi-Fi address, the last move, and who to tell about the next one."""

    def __init__(
        self,
        memory: AddressMemory,
        detect: Callable[[], str | None],
        *,
        every: float | None = None,
    ) -> None:
        self._memory = memory
        self._detect = detect
        self._every = every
        self._listeners: list[MoveListener] = []
        self._address_listeners: list[AddressListener] = []
        self.ip: str | None = None
        self.moved: Move | None = None

    def on_move(self, listener: MoveListener) -> None:
        """Called when the address differs from the one remembered (another network)."""
        self._listeners.append(listener)

    def on_address(self, listener: AddressListener) -> None:
        """Called whenever a check finds a new address, including the first one after
        starting offline (at login, before the Wi-Fi connects)."""
        self._address_listeners.append(listener)

    async def start(self, ip: str | None) -> None:
        """Set the address found at startup; tells listeners if it changed since last run."""
        self.ip = ip
        if ip is not None:
            await self._record(ip)

    async def check(self) -> Move | None:
        """Look up the address once. Offline (no address) keeps the last one."""
        ip = await asyncio.to_thread(self._detect)
        if ip is None or ip == self.ip:
            return None
        self.ip = ip
        log_event(log, "network_address", lanIp=ip)
        for listener in list(self._address_listeners):
            await _call(listener, ip)
        return await self._record(ip)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(CHECK_SECONDS if self._every is None else self._every)
            try:
                await self.check()
            except Exception as exc:
                log_event(log, "network_check_failed", level=logging.WARNING, error=str(exc))

    async def _record(self, ip: str) -> Move | None:
        move = self._memory.record(ip)
        if move is None:
            return None
        self.moved = move
        log_event(log, "network_changed", previous=move.previous, lanIp=move.current)
        for listener in list(self._listeners):
            await _call(listener, move)
        return move


async def _call(listener: Callable[[Any], Awaitable[None] | None], value: object) -> None:
    """Run one listener; a failing one must not block the others."""
    try:
        result = listener(value)
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        log_event(log, "network_listener_failed", level=logging.WARNING, error=str(exc))

"""A connected phone and the hub of all connections."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import secrets
from collections.abc import Callable, Iterator

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from lapremote.protocol import Role, WireModel, encode
from lapremote.security.pairing import Device
from lapremote.security.ratelimit import Clock, Limits, TokenBucket


class Connection:
    def __init__(self, ws: WebSocket, ip: str, limits: Limits, clock: Clock) -> None:
        self.ws = ws
        self.ip = ip
        self.conn_id = secrets.token_hex(4)
        self.device: Device | None = None
        self.messages = TokenBucket(limits.messages_per_second, clock=clock)
        self.key_text = TokenBucket(limits.key_text_per_second, clock=clock)
        # Artwork ids already sent on this connection (media.state sends each image once).
        self.sent_artwork: set[str] = set()
        self._send_lock = asyncio.Lock()
        self._seq = itertools.count(1)
        self.closed = False

    @property
    def authed(self) -> bool:
        return self.device is not None

    @property
    def role(self) -> Role | None:
        return self.device.role if self.device is not None else None

    @property
    def device_id(self) -> str | None:
        return self.device.device_id if self.device is not None else None

    async def send(self, type_: str, payload: WireModel) -> bool:
        text = encode(type_, payload, f"s{next(self._seq)}")
        async with self._send_lock:
            if self.closed or self.ws.application_state != WebSocketState.CONNECTED:
                return False
            try:
                await self.ws.send_text(text)
            except (WebSocketDisconnect, RuntimeError, OSError):
                self.closed = True
                return False
        return True

    async def send_bytes(self, data: bytes) -> bool:
        async with self._send_lock:
            if self.closed or self.ws.application_state != WebSocketState.CONNECTED:
                return False
            try:
                await self.ws.send_bytes(data)
            except (WebSocketDisconnect, RuntimeError, OSError):
                self.closed = True
                return False
        return True

    async def close(self, code: int, reason: str) -> None:
        async with self._send_lock:
            if self.closed:
                return
            self.closed = True
            if self.ws.application_state == WebSocketState.CONNECTED:
                with contextlib.suppress(RuntimeError, OSError):
                    await self.ws.close(code=code, reason=reason)


class Hub:
    def __init__(self) -> None:
        self._connections: set[Connection] = set()

    def add(self, conn: Connection) -> None:
        self._connections.add(conn)

    def remove(self, conn: Connection) -> None:
        self._connections.discard(conn)

    def __iter__(self) -> Iterator[Connection]:
        return iter(list(self._connections))

    def authed(self) -> list[Connection]:
        return [c for c in self._connections if c.authed and not c.closed]

    def for_device(self, device_id: str) -> list[Connection]:
        return [c for c in self.authed() if c.device_id == device_id]

    def is_online(self, device_id: str) -> bool:
        return bool(self.for_device(device_id))

    async def broadcast(
        self,
        type_: str,
        payload: WireModel,
        where: Callable[[Connection], bool] | None = None,
    ) -> None:
        targets = [c for c in self.authed() if where is None or where(c)]
        if targets:
            await asyncio.gather(*(c.send(type_, payload) for c in targets))

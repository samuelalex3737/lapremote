"""The agent: shared state plus the core handlers (auth, ping, devices).

Feature modules (input, media, ...) register their own handlers on
``agent.router`` and flip their entry in ``agent.feature_status``.
"""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from lapremote.config import Config
from lapremote.connection import Connection, Hub
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import (
    AuthOk,
    AuthPair,
    AuthResume,
    DeviceInfo,
    DevicesRevoke,
    DevicesRole,
    DevicesState,
    Empty,
    Features,
    FeatureStatus,
    Ping,
    Pong,
    Toast,
)
from lapremote.router import ActionError, AuthRejectedError, Router
from lapremote.security.pairing import (
    Device,
    DeviceStore,
    LastOwnerError,
    PairingManager,
    UnknownDeviceError,
)
from lapremote.security.ratelimit import Clock, Limits, SlidingWindowLimiter
from lapremote.system.platform_info import detect_os

FEATURE_NAMES: tuple[str, ...] = (
    "input",
    "media",
    "volume",
    "brightness",
    "preview",
    "context",
    "power",
    "launcher",
    "scenes",
    "timer",
    "ai",
)
NOT_YET = "Not available in this version yet."
CLOSE_REVOKED = 4003
CLOSE_REVOKED_REASON = "revoked"

ConnectHook = Callable[[Connection], Awaitable[None]]


class Agent:
    def __init__(
        self,
        config: Config,
        data_dir: Path,
        *,
        limits: Limits | None = None,
        clock: Clock = time.monotonic,
        wall_clock: Clock = time.time,
        host_name: str | None = None,
    ) -> None:
        self.config = config
        self.data_dir = data_dir
        self.limits = limits or Limits()
        self.clock = clock
        self.log = get_logger("agent")
        self.hub = Hub()
        self.router = Router()
        self.devices = DeviceStore(data_dir / "devices.json", clock=wall_clock)
        self._code_listeners: list[Callable[[str], None]] = []
        self.pairing = PairingManager(clock=clock, on_rotate=self._code_rotated)
        self.pair_limiter = SlidingWindowLimiter(
            self.limits.pair_attempts, self.limits.pair_window_seconds, clock=clock
        )
        self.host_name = host_name or socket.gethostname()
        self.os = detect_os()
        self.feature_status: dict[str, FeatureStatus] = {
            name: FeatureStatus(available=False, reason=NOT_YET) for name in FEATURE_NAMES
        }
        self.on_connect: list[ConnectHook] = []
        self.on_disconnect: list[ConnectHook] = []
        self._background: set[asyncio.Task[None]] = set()
        self._register_core()

    # ------------------------------------------------------------------ setup

    def _register_core(self) -> None:
        self.router.register("auth.pair", self._auth_pair)
        self.router.register("auth.resume", self._auth_resume)
        self.router.register("ping", self._ping)
        self.router.register("devices.list", self._devices_list)
        self.router.register("devices.revoke", self._devices_revoke)
        self.router.register("devices.role", self._devices_role)

    def add_code_listener(self, listener: Callable[[str], None]) -> None:
        self._code_listeners.append(listener)

    def _code_rotated(self, code: str) -> None:
        for listener in self._code_listeners:
            listener(code)

    def set_feature(self, name: str, available: bool, reason: str | None = None) -> None:
        if name not in self.feature_status:
            msg = f"unknown feature {name!r}"
            raise KeyError(msg)
        self.feature_status[name] = FeatureStatus(available=available, reason=reason)

    def features(self) -> Features:
        return Features(**self.feature_status, secure_context=self.config.https.enabled)

    def spawn(self, coro: Awaitable[None]) -> None:
        """Run a coroutine in the background, keeping a reference until it finishes."""

        async def runner() -> None:
            await coro

        task = asyncio.get_running_loop().create_task(runner())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    # ------------------------------------------------------------------ auth

    async def _auth_pair(self, conn: Connection, payload: AuthPair) -> None:
        if not self.pair_limiter.allow(conn.ip):
            raise AuthRejectedError("rate_limited")
        result = self.pairing.consume(payload.code)
        if result == "expired":
            raise AuthRejectedError("expired_code")
        if result != "ok":
            raise AuthRejectedError("invalid_code")
        device, token = self.devices.add(payload.device_name, payload.platform)
        log_event(self.log, "device_paired", device=device.device_id, role=device.role)
        await self._authenticated(conn, device, token)

    async def _auth_resume(self, conn: Connection, payload: AuthResume) -> None:
        device = self.devices.verify(payload.device_id, payload.token)
        if device is None:
            raise AuthRejectedError("bad_token")
        await self._authenticated(conn, device, None)

    async def _authenticated(self, conn: Connection, device: Device, token: str | None) -> None:
        conn.device = device
        await conn.send(
            "auth.ok",
            AuthOk(
                device_id=device.device_id,
                token=token,
                role=device.role,
                host_name=self.host_name,
                os=self.os,
                features=self.features(),
            ),
        )
        for hook in self.on_connect:
            await hook(conn)
        await self.broadcast_devices()

    async def disconnected(self, conn: Connection) -> None:
        self.hub.remove(conn)
        for hook in self.on_disconnect:
            try:
                await hook(conn)
            except Exception:
                self.log.exception("disconnect_hook_failed")
        if conn.device is not None:
            self.devices.touch(conn.device.device_id)
            await self.broadcast_devices()

    # ------------------------------------------------------------------ misc

    async def _ping(self, conn: Connection, payload: Ping) -> None:
        await conn.send("pong", Pong(t=payload.t))

    def devices_state(self) -> DevicesState:
        return DevicesState(
            devices=[
                DeviceInfo(
                    device_id=d.device_id,
                    name=d.name,
                    platform=d.platform,
                    role=d.role,
                    paired_at=d.paired_at,
                    last_seen_at=d.last_seen_at,
                    online=self.hub.is_online(d.device_id),
                )
                for d in self.devices.list()
            ]
        )

    async def broadcast_devices(self) -> None:
        await self.hub.broadcast(
            "devices.state", self.devices_state(), where=lambda c: c.role == "owner"
        )

    async def _devices_list(self, conn: Connection, _payload: Empty) -> None:
        await conn.send("devices.state", self.devices_state())

    async def _devices_revoke(self, conn: Connection, payload: DevicesRevoke) -> None:
        try:
            device = self.devices.revoke(payload.device_id)
        except UnknownDeviceError as exc:
            raise ActionError("That device isn't paired.") from exc
        except LastOwnerError as exc:
            raise ActionError("Make another device the owner first.") from exc
        log_event(self.log, "device_revoked", device=device.device_id, by=conn.device_id)
        targets = self.hub.for_device(device.device_id)
        for target in targets:
            target.device = None
        self.spawn(self._close_all(targets))
        await self.broadcast_devices()

    async def _close_all(self, conns: list[Connection]) -> None:
        # Yield first so the ack for the revoke request goes out before the socket closes.
        await asyncio.sleep(0)
        for target in conns:
            await target.close(CLOSE_REVOKED, CLOSE_REVOKED_REASON)

    async def _devices_role(self, conn: Connection, payload: DevicesRole) -> None:
        try:
            device = self.devices.set_role(payload.device_id, payload.role)
        except UnknownDeviceError as exc:
            raise ActionError("That device isn't paired.") from exc
        except LastOwnerError as exc:
            raise ActionError("Make another device the owner first.") from exc
        log_event(self.log, "device_role", device=device.device_id, role=device.role)
        message = (
            "You're now an owner of this laptop."
            if device.role == "owner"
            else "You're now a guest on this laptop."
        )
        for target in self.hub.for_device(device.device_id):
            if target is not conn:
                await target.send("toast", Toast(level="info", message=message))
        await self.broadcast_devices()

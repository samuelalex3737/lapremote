"""Advertise the agent on the LAN with mDNS: ``_lapremote._tcp`` and ``lapremote.local``.

This is a secondary path. The QR code with the LAN IP is the primary one, so a
failure here is logged and never stops the agent.
"""

from __future__ import annotations

import socket

from zeroconf import IPVersion
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

from lapremote import __version__
from lapremote.logging_setup import get_logger, log_event

SERVICE_TYPE = "_lapremote._tcp.local."
HOST_NAME = "lapremote.local."

log = get_logger("discovery")


def build_service_info(ip: str, port: int, instance: str) -> AsyncServiceInfo:
    safe_instance = "".join(ch for ch in instance if ch.isalnum() or ch in " -")[:40] or "Laptop"
    return AsyncServiceInfo(
        SERVICE_TYPE,
        f"LapRemote on {safe_instance}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={"v": "1", "version": __version__, "path": "/"},
        server=HOST_NAME,
    )


class Advertiser:
    def __init__(self) -> None:
        self._zc: AsyncZeroconf | None = None
        self._info: AsyncServiceInfo | None = None

    async def start(self, ip: str, port: int, instance: str) -> bool:
        try:
            self._zc = AsyncZeroconf(interfaces=[ip], ip_version=IPVersion.V4Only)
            self._info = build_service_info(ip, port, instance)
            await self._zc.async_register_service(self._info, allow_name_change=True)
        except (OSError, RuntimeError, ValueError) as exc:
            log_event(log, "mdns_failed", level=30, error=str(exc))
            await self.stop()
            return False
        log_event(log, "mdns_advertised", service=SERVICE_TYPE, host=HOST_NAME, port=port)
        return True

    async def stop(self) -> None:
        zc, info = self._zc, self._info
        self._zc, self._info = None, None
        if zc is None:
            return
        try:
            if info is not None:
                await zc.async_unregister_service(info)
        finally:
            await zc.async_close()

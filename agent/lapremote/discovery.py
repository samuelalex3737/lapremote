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


def build_service_info(
    ip: str, port: int, instance: str, extra: dict[str, str] | None = None
) -> AsyncServiceInfo:
    """``extra`` adds TXT fields other LapRemote laptops read: id, name, mac and https."""
    safe_instance = "".join(ch for ch in instance if ch.isalnum() or ch in " -")[:40] or "Laptop"
    properties = {"v": "1", "version": __version__, "path": "/", **(extra or {})}
    # Two laptops with the same computer name would announce the same service name and one
    # would hide the other, so the laptop's own id goes into the name too.
    agent_id = properties.get("id", "")
    suffix = f" ({agent_id[:6]})" if agent_id else ""
    return AsyncServiceInfo(
        SERVICE_TYPE,
        f"LapRemote on {safe_instance}{suffix}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties=properties,
        server=HOST_NAME,
    )


class Advertiser:
    def __init__(self) -> None:
        self._zc: AsyncZeroconf | None = None
        self._info: AsyncServiceInfo | None = None

    @property
    def zeroconf(self) -> AsyncZeroconf | None:
        return self._zc

    async def start(
        self, ip: str, port: int, instance: str, extra: dict[str, str] | None = None
    ) -> bool:
        try:
            self._zc = AsyncZeroconf(interfaces=[ip], ip_version=IPVersion.V4Only)
            self._info = build_service_info(ip, port, instance, extra)
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

"""Other LapRemote laptops on the network, and Wake-on-LAN.

Every agent advertises ``_lapremote._tcp`` with a stable random id and its network card's
address (MAC) in the TXT record, and browses for the others. The phone gets the list in
``peers.state``: online laptops it can switch to, and recently seen ones that are asleep, which an
awake laptop can wake with a magic packet (a browser can't send one itself).

A phone pairs with each laptop separately; switching only opens the other laptop's page.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import secrets
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import psutil
from pydantic import TypeAdapter, ValidationError
from zeroconf.asyncio import AsyncServiceBrowser

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import PeerInfo, PeersState, WolWake
from lapremote.router import ActionError
from lapremote.storage import write_json_atomic

if TYPE_CHECKING:
    from zeroconf import Zeroconf

log = get_logger("peers")

AGENT_ID_FILE = "agent-id"
PEERS_FILE = "peers.json"
MAX_PEERS = 20
FORGET_AFTER_SECONDS = 60 * 24 * 3600
WOL_PORTS = (9, 7)
HEALTH_EVERY_SECONDS = 20.0
HEALTH_TIMEOUT = 3.0
HEALTH_MISSES = 2
_LIST = TypeAdapter(list[PeerInfo])


def agent_id(data_dir: Path) -> str:
    """A random id for this laptop, made once and kept in the data folder."""
    path = data_dir / AGENT_ID_FILE
    try:
        value = path.read_text(encoding="ascii").strip()
        if len(value) == 16 and all(c in "0123456789abcdef" for c in value):
            return value
    except OSError:
        pass
    value = secrets.token_hex(8)
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="ascii")
    return value


def normalise_mac(value: str) -> str | None:
    hexdigits = "".join(c for c in value.upper() if c in "0123456789ABCDEF")
    if len(hexdigits) != 12 or hexdigits in ("000000000000", "FFFFFFFFFFFF"):
        return None
    return ":".join(hexdigits[i : i + 2] for i in range(0, 12, 2))


def mac_for_ip(ip: str | None) -> str | None:
    """The MAC address of the network card that has ``ip``."""
    if ip is None:
        return None
    for addrs in psutil.net_if_addrs().values():
        if any(a.family == socket.AF_INET and a.address == ip for a in addrs):
            for a in addrs:
                if a.family == psutil.AF_LINK:
                    return normalise_mac(a.address)
    return None


def broadcast_addresses(ip: str | None) -> list[str]:
    """Where to send a magic packet: everyone, plus this network's own broadcast address."""
    targets = ["255.255.255.255"]
    if ip is None:
        return targets
    for addrs in psutil.net_if_addrs().values():
        for a in addrs:
            if a.family == socket.AF_INET and a.address == ip and a.netmask:
                network = ipaddress.ip_network(f"{ip}/{a.netmask}", strict=False)
                targets.append(str(network.broadcast_address))
    return list(dict.fromkeys(targets))


HealthCheck = Callable[[str], Awaitable[bool]]


async def check_health(url: str) -> bool:
    """True when the LapRemote at ``url`` answers its health check."""
    try:
        # verify=False: a laptop's mkcert certificate may not be trusted here, and the check
        # sends nothing and reads only "ok".
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT, verify=False) as client:  # noqa: S501
            response = await client.get(url.rstrip("/") + "/api/health")
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(mac.replace(":", ""))
    return b"\xff" * 6 + raw * 16


def send_magic_packet(mac: str, targets: list[str]) -> None:
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for target in targets:
            for port in WOL_PORTS:
                sock.sendto(packet, (target, port))


@dataclass
class Sighting:
    """One laptop found on the network (from its mDNS record)."""

    peer_id: str
    name: str
    url: str
    mac: str | None


def parse_txt(properties: dict[bytes, bytes | None]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in properties.items():
        if value is None:
            continue
        try:
            out[key.decode("ascii")] = value.decode("utf-8")[:128]
        except UnicodeDecodeError:
            continue
    return out


def sighting_from(properties: dict[bytes, bytes | None], ip: str, port: int) -> Sighting | None:
    txt = parse_txt(properties)
    peer_id = txt.get("id", "")
    if len(peer_id) != 16 or not all(c in "0123456789abcdef" for c in peer_id):
        return None
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if address.version != 4 or not (address.is_private or address.is_link_local):
        return None  # only laptops on this local network
    if not 1 <= port <= 65535:
        return None
    scheme = "https" if txt.get("https") == "1" else "http"
    name = "".join(c for c in txt.get("name", "") if c.isprintable())[:64].strip() or "Laptop"
    return Sighting(
        peer_id=peer_id,
        name=name,
        url=f"{scheme}://{ip}:{port}/",
        mac=normalise_mac(txt.get("mac", "")),
    )


class PeerService:
    def __init__(
        self,
        agent: Agent,
        own_id: str,
        *,
        clock: Callable[[], float] = time.time,
        sender: Callable[[str, list[str]], None] = send_magic_packet,
        checker: HealthCheck | None = None,
        check_every: float = HEALTH_EVERY_SECONDS,
    ) -> None:
        self._agent = agent
        self._checker = checker or check_health
        self._check_every = check_every
        self._misses: dict[str, int] = {}
        self._health: asyncio.Task[None] | None = None
        self._own_id = own_id
        self._clock = clock
        self._sender = sender
        self._path = agent.data_dir / PEERS_FILE
        self._known: dict[str, PeerInfo] = {}
        self._online: set[str] = set()
        self._lan_ip: str | None = None
        self._watcher: AsyncServiceBrowser | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._load()

    @property
    def own_id(self) -> str:
        return self._own_id

    def register(self) -> None:
        self._agent.router.register("wol.wake", self._wake)
        self._agent.on_connect.append(self._send_state)

    def _load(self) -> None:
        try:
            peers = _LIST.validate_json(self._path.read_bytes())
        except (OSError, ValidationError, ValueError):
            return
        cutoff = (self._clock() - FORGET_AFTER_SECONDS) * 1000
        for peer in peers:
            if peer.peer_id != self._own_id and (peer.last_seen_at or 0) >= cutoff:
                self._known[peer.peer_id] = peer.model_copy(update={"online": False})

    def _save(self) -> None:
        items = sorted(self._known.values(), key=lambda p: -(p.last_seen_at or 0))[:MAX_PEERS]
        write_json_atomic(self._path, [p.model_dump(mode="json", by_alias=True) for p in items])

    def state(self) -> PeersState:
        peers = [
            p.model_copy(update={"online": p.peer_id in self._online})
            for p in sorted(self._known.values(), key=lambda p: p.name.lower())
        ]
        return PeersState(peers=peers)

    async def _send_state(self, conn: Connection) -> None:
        if conn.role == "owner":
            await conn.send("peers.state", self.state())

    async def _broadcast(self) -> None:
        await self._agent.hub.broadcast(
            "peers.state", self.state(), where=lambda c: c.role == "owner"
        )

    async def seen(self, sighting: Sighting) -> None:
        if sighting.peer_id == self._own_id:
            return
        previous = self._known.get(sighting.peer_id)
        peer = PeerInfo(
            peer_id=sighting.peer_id,
            name=sighting.name,
            url=sighting.url,
            online=True,
            mac=sighting.mac or (previous.mac if previous else None),
            last_seen_at=self._clock() * 1000,
        )
        changed = (
            previous is None
            or sighting.peer_id not in self._online
            or (previous.name, previous.url, previous.mac) != (peer.name, peer.url, peer.mac)
        )
        self._known[peer.peer_id] = peer
        self._online.add(peer.peer_id)
        if len(self._known) > MAX_PEERS:
            oldest = min(self._known.values(), key=lambda p: p.last_seen_at or 0)
            self._known.pop(oldest.peer_id, None)
        if changed:
            self._save()
            log_event(log, "peer_seen", peer=peer.peer_id)
            await self._broadcast()

    async def gone(self, peer_id: str) -> None:
        if peer_id in self._online:
            self._online.discard(peer_id)
            log_event(log, "peer_gone", peer=peer_id)
            await self._broadcast()

    async def _wake(self, conn: Connection, p: WolWake) -> None:
        peer = next((x for x in self._known.values() if x.mac == p.mac), None)
        if peer is None:
            raise ActionError("That laptop isn't one this laptop has seen.")
        targets = broadcast_addresses(self._lan_ip)
        try:
            await asyncio.to_thread(self._sender, p.mac, targets)
        except OSError as exc:
            raise ActionError("Couldn't send the wake signal.") from exc
        log_event(log, "wake_sent", peer=peer.peer_id, by=conn.device_id)

    # ------------------------------------------------------------------ mDNS

    def _keep(self, task: asyncio.Task[None]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start_watching(self, zeroconf: Zeroconf, lan_ip: str | None) -> None:
        """Browse for other agents with the advertiser's Zeroconf instance."""
        from zeroconf import DNSQuestionType, ServiceStateChange  # noqa: PLC0415
        from zeroconf.asyncio import AsyncServiceInfo  # noqa: PLC0415

        from lapremote.discovery import SERVICE_TYPE  # noqa: PLC0415

        self._lan_ip = lan_ip
        self.start_health_checks()
        loop = asyncio.get_running_loop()
        names: dict[str, str] = {}

        async def resolve(name: str) -> None:
            info = AsyncServiceInfo(SERVICE_TYPE, name)
            if not await info.async_request(zeroconf, 3000):
                return
            addresses = info.parsed_addresses()
            if not addresses or info.port is None:
                return
            sighting = sighting_from(info.properties, addresses[0], info.port)
            if sighting is not None:
                names[name] = sighting.peer_id
                await self.seen(sighting)

        def on_change(
            zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
        ) -> None:
            if state_change is ServiceStateChange.Removed:
                peer_id = names.pop(name, None)
                if peer_id is not None:
                    self._keep(loop.create_task(self.gone(peer_id)))
            else:
                self._keep(loop.create_task(resolve(name)))

        try:
            # Ask for answers sent to everyone (QM): a direct reply to the first question only
            # reaches one program when several share the mDNS port on the same computer.
            self._watcher = AsyncServiceBrowser(
                zeroconf, SERVICE_TYPE, handlers=[on_change], question_type=DNSQuestionType.QM
            )
        except (OSError, RuntimeError) as exc:
            log_event(log, "peer_browse_failed", level=30, error=str(exc))

    async def stop_watching(self) -> None:
        watcher, self._watcher = self._watcher, None
        if watcher is not None:
            await watcher.async_cancel()
        health, self._health = self._health, None
        if health is not None:
            health.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await health

    def start_health_checks(self) -> None:
        """A sleeping laptop says no goodbye on the network, so check the online ones now and
        then, and mark one asleep after it misses two checks in a row."""
        if self._health is None:
            self._health = asyncio.get_running_loop().create_task(self._health_loop())

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(self._check_every)
            await self.check_online()

    async def check_online(self) -> None:
        for peer_id in list(self._online):
            peer = self._known.get(peer_id)
            if peer is None:
                continue
            if await self._checker(peer.url):
                self._misses.pop(peer_id, None)
                continue
            self._misses[peer_id] = self._misses.get(peer_id, 0) + 1
            if self._misses[peer_id] >= HEALTH_MISSES:
                self._misses.pop(peer_id, None)
                await self.gone(peer_id)

"""Pick the LAN IPv4 address the phone should use.

Prefers the interface that holds the default route and skips virtual adapters
(VirtualBox, VMware, Hyper-V / WSL, Docker, VPNs) so the QR code points at the
real Wi-Fi or Ethernet address.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass

import psutil

VIRTUAL_MARKERS: tuple[str, ...] = (
    "virtualbox",
    "vboxnet",
    "vmware",
    "vmnet",
    "vethernet",
    "hyper-v",
    "wsl",
    "docker",
    "br-",
    "veth",
    "virbr",
    "tailscale",
    "zerotier",
    "hamachi",
    "wireguard",
    "tap",
    "tun",
    "utun",
    "npcap",
    "loopback",
    "bluetooth",
)
PREFERRED_MARKERS: tuple[str, ...] = ("wi-fi", "wifi", "wlan", "wireless", "ethernet", "en0", "eth")


@dataclass(frozen=True)
class Interface:
    name: str
    ip: str


def is_virtual(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in VIRTUAL_MARKERS)


def is_lan_ip(ip: str) -> bool:
    try:
        addr = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError:
        return False
    return addr.is_private and not addr.is_loopback and not addr.is_link_local


def default_route_ip() -> str | None:
    """Source address the OS would use for outbound traffic. No packet is sent."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed
        except OSError:
            return None
        ip: str = sock.getsockname()[0]
    return ip if is_lan_ip(ip) else None


def list_interfaces() -> list[Interface]:
    stats = psutil.net_if_stats()
    found: list[Interface] = []
    for name, addrs in psutil.net_if_addrs().items():
        stat = stats.get(name)
        if stat is None or not stat.isup:
            continue
        found.extend(
            Interface(name, addr.address)
            for addr in addrs
            if addr.family == socket.AF_INET and is_lan_ip(addr.address)
        )
    return found


def pick_lan_ip(default_ip: str | None, interfaces: list[Interface]) -> str | None:
    """Choose the best LAN address from the default-route IP and the interface list."""
    real = [i for i in interfaces if not is_virtual(i.name)]
    if default_ip is not None:
        owner = next((i for i in interfaces if i.ip == default_ip), None)
        if owner is None or not is_virtual(owner.name):
            return default_ip
    for marker in PREFERRED_MARKERS:
        for iface in real:
            if marker in iface.name.lower():
                return iface.ip
    if real:
        return real[0].ip
    return default_ip


def detect_lan_ip() -> str | None:
    return pick_lan_ip(default_route_ip(), list_interfaces())

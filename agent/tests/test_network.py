from __future__ import annotations

import pytest

from lapremote.system.network import (
    Interface,
    is_lan_ip,
    is_virtual,
    list_interfaces,
    pick_lan_ip,
)

WIFI = Interface("Wi-Fi", "192.168.1.20")
WSL = Interface("vEthernet (WSL (Hyper-V firewall))", "172.20.64.1")
VBOX = Interface("VirtualBox Host-Only Network", "192.168.56.1")
DOCKER = Interface("docker0", "172.17.0.1")
ETH = Interface("Ethernet", "10.0.0.5")


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("192.168.1.20", True),
        ("10.0.0.5", True),
        ("172.16.4.4", True),
        ("127.0.0.1", False),
        ("169.254.10.10", False),
        ("8.8.8.8", False),
        ("not-an-ip", False),
    ],
)
def test_is_lan_ip(ip: str, expected: bool) -> None:
    assert is_lan_ip(ip) is expected


def test_virtual_detection() -> None:
    assert is_virtual(WSL.name)
    assert is_virtual(VBOX.name)
    assert is_virtual(DOCKER.name)
    assert not is_virtual(WIFI.name)
    assert not is_virtual(ETH.name)


def test_default_route_wins_when_real() -> None:
    assert pick_lan_ip("192.168.1.20", [WSL, VBOX, WIFI]) == "192.168.1.20"


def test_default_route_on_virtual_adapter_is_skipped() -> None:
    assert pick_lan_ip("172.20.64.1", [WSL, VBOX, WIFI]) == "192.168.1.20"


def test_prefers_wifi_then_ethernet_without_default_route() -> None:
    assert pick_lan_ip(None, [VBOX, ETH, WIFI]) == "192.168.1.20"
    assert pick_lan_ip(None, [VBOX, ETH]) == "10.0.0.5"


def test_unknown_default_route_ip_is_trusted() -> None:
    assert pick_lan_ip("10.1.1.1", [VBOX]) == "10.1.1.1"


def test_nothing_usable() -> None:
    assert pick_lan_ip(None, [WSL, VBOX]) is None
    assert pick_lan_ip(None, []) is None


def test_list_interfaces_on_this_host_returns_lan_addresses() -> None:
    for iface in list_interfaces():
        assert is_lan_ip(iface.ip)

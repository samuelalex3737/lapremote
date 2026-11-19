from __future__ import annotations

import shutil
import sys

import pytest

from lapremote.system.platform_info import (
    UnsupportedPlatformError,
    detect_display_server,
    detect_media_cli,
    detect_os,
    detect_platform,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("win32", "windows"), ("darwin", "macos"), ("linux", "linux")],
)
def test_detect_os(value: str, expected: str) -> None:
    assert detect_os(value) == expected


def test_detect_os_rejects_unknown() -> None:
    with pytest.raises(UnsupportedPlatformError):
        detect_os("freebsd14")


def test_display_server_only_reported_on_linux() -> None:
    assert detect_display_server("windows", {"XDG_SESSION_TYPE": "wayland"}) is None
    assert detect_display_server("macos", {}) is None


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"XDG_SESSION_TYPE": "wayland"}, "wayland"),
        ({"XDG_SESSION_TYPE": "X11"}, "x11"),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
        ({"DISPLAY": ":0"}, "x11"),
        ({}, "unknown"),
    ],
)
def test_display_server_on_linux(env: dict[str, str], expected: str) -> None:
    assert detect_display_server("linux", env) == expected


def test_media_cli_none_on_windows() -> None:
    assert detect_media_cli("windows") is None


def test_media_cli_found_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/opt/homebrew/bin/media-control" if name == "media-control" else None,
    )
    mac = detect_media_cli("macos")
    assert mac is not None
    assert mac.name == "media-control"
    assert mac.found
    linux = detect_media_cli("linux")
    assert linux is not None
    assert linux.name == "playerctl"
    assert not linux.found


def test_detect_platform_on_this_host() -> None:
    info = detect_platform()
    assert info.os == detect_os(sys.platform)
    assert info.python_version.startswith("3.12")
    assert info.hostname
    assert info.os_version
    dumped = info.model_dump(by_alias=True)
    assert "osVersion" in dumped
    assert "pythonVersion" in dumped

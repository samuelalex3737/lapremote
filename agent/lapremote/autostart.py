"""Start LapRemote when the person logs in.

Windows: a value under HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
macOS: ~/Library/LaunchAgents/com.lapremote.agent.plist.
Linux: ~/.config/autostart/lapremote.desktop (XDG autostart).

The command is built here from the running interpreter or the packaged executable. Nothing
from the phone or the network ever goes into it.
"""

from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from lapremote.protocol import OsName

APP_NAME = "LapRemote"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
MAC_LABEL = "com.lapremote.agent"


def launch_command() -> list[str]:
    """How to start the agent with no console window, as separate arguments."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = Path(sys.executable)
    if sys.platform == "win32":
        windowless = exe.with_name("pythonw.exe")
        if windowless.is_file():
            exe = windowless
    return [str(exe), "-m", "lapremote"]


def windows_command_line(args: list[str]) -> str:
    return subprocess.list2cmdline(args)


class Autostart(Protocol):
    def is_enabled(self) -> bool: ...
    def enable(self) -> None: ...
    def disable(self) -> None: ...


class RegistryLike(Protocol):
    """The three registry operations we need, so tests can use a fake."""

    def get(self, key: str, name: str) -> str | None: ...
    def set(self, key: str, name: str, value: str) -> None: ...
    def delete(self, key: str, name: str) -> None: ...


class CurrentUserRegistry:
    """HKEY_CURRENT_USER through winreg (Windows only)."""

    def get(self, key: str, name: str) -> str | None:
        import winreg  # noqa: PLC0415 - Windows only

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                value, _kind = winreg.QueryValueEx(handle, name)
        except FileNotFoundError:
            return None
        return str(value)

    def set(self, key: str, name: str, value: str) -> None:
        import winreg  # noqa: PLC0415 - Windows only

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
            winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)

    def delete(self, key: str, name: str) -> None:
        import winreg  # noqa: PLC0415 - Windows only

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as handle:
                winreg.DeleteValue(handle, name)
        except FileNotFoundError:
            return


class WindowsAutostart:
    def __init__(self, registry: RegistryLike, command: list[str], key: str = RUN_KEY) -> None:
        self._registry = registry
        self._command = windows_command_line(command)
        self._key = key

    def is_enabled(self) -> bool:
        return self._registry.get(self._key, APP_NAME) == self._command

    def enable(self) -> None:
        self._registry.set(self._key, APP_NAME, self._command)

    def disable(self) -> None:
        self._registry.delete(self._key, APP_NAME)


class MacAutostart:
    def __init__(self, agents_dir: Path, command: list[str]) -> None:
        self._path = agents_dir / f"{MAC_LABEL}.plist"
        self._command = command

    def _plist(self) -> bytes:
        return plistlib.dumps(
            {
                "Label": MAC_LABEL,
                "ProgramArguments": self._command,
                "RunAtLoad": True,
                "ProcessType": "Interactive",
            }
        )

    def is_enabled(self) -> bool:
        return self._path.is_file() and self._path.read_bytes() == self._plist()

    def enable(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(self._plist())

    def disable(self) -> None:
        self._path.unlink(missing_ok=True)


class LinuxAutostart:
    def __init__(self, autostart_dir: Path, command: list[str]) -> None:
        self._path = autostart_dir / "lapremote.desktop"
        self._command = command

    def _entry(self) -> str:
        return "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name={APP_NAME}",
                "Comment=Control this laptop from your phone",
                f"Exec={shlex.join(self._command)}",
                "X-GNOME-Autostart-enabled=true",
                "Terminal=false",
                "",
            ]
        )

    def is_enabled(self) -> bool:
        return self._path.is_file() and self._path.read_text(encoding="utf-8") == self._entry()

    def enable(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self._entry(), encoding="utf-8")

    def disable(self) -> None:
        self._path.unlink(missing_ok=True)


def create_autostart(os_name: OsName, command: list[str] | None = None) -> Autostart:
    command = command or launch_command()
    if os_name == "windows":
        return WindowsAutostart(CurrentUserRegistry(), command)
    if os_name == "macos":
        return MacAutostart(Path.home() / "Library" / "LaunchAgents", command)
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return LinuxAutostart(Path(config_home) / "autostart", command)

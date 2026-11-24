"""Start LapRemote when the person logs in.

Windows: a Task Scheduler task that runs when this user signs in (no admin needed). The
Run registry key was used before, but Windows skipped it silently on a real laptop
(Windows 11 build 26300), so creating the task also removes the old Run value.
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
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from xml.sax.saxutils import escape

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


TASK_NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"
# How long a read of the task is trusted: the dashboard asks every few seconds.
TASK_CACHE_SECONDS = 30.0

TaskRunner = Callable[[list[str]], tuple[int, str]]


def run_schtasks(args: list[str]) -> tuple[int, str]:
    """Run schtasks.exe with no console window; returns the exit code and its output."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(  # noqa: S603 - fixed program, arguments built here
            ["schtasks.exe", *args],  # noqa: S607 - a Windows system tool
            capture_output=True,
            timeout=20,
            check=False,
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        msg = f"schtasks failed: {exc}"
        raise OSError(msg) from exc
    # schtasks prints in the console code page, whatever the XML header says.
    codec = "oem" if sys.platform == "win32" else "utf-8"
    return done.returncode, (done.stdout or done.stderr).decode(codec, errors="replace")


def current_windows_user() -> str:
    """DOMAIN\\user for the signed-in person: the task runs only for them."""
    if sys.platform == "win32":
        import ctypes  # noqa: PLC0415 - Windows only

        size = ctypes.c_ulong(256)
        buffer = ctypes.create_unicode_buffer(size.value)
        # 2 = NameSamCompatible, such as LAPTOP-1234\sam
        if ctypes.windll.secur32.GetUserNameExW(2, buffer, ctypes.byref(size)):
            return str(buffer.value)
    return f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"


TASK_TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>LapRemote</Author>
    <Description>Starts LapRemote, the phone remote for this laptop, when you sign in. \
Turn it off with Start at login in the LapRemote tray menu.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{program}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def task_xml(command: list[str], user: str) -> str:
    """Start at this user's sign-in, keep running (on battery too), retry after a crash."""
    return TASK_TEMPLATE.format(
        user=escape(user),
        program=escape(command[0]),
        arguments=escape(windows_command_line(command[1:])),
    )


def task_matches(xml_text: str, command: list[str]) -> bool:
    """Whether the registered task is turned on and runs this command."""
    start = xml_text.find("<Task")
    if start < 0:
        return False
    try:
        root = ET.fromstring(xml_text[start:])  # noqa: S314 - schtasks output, not the network
    except ET.ParseError:
        return False

    def text(*names: str) -> str:
        found = root.find("/".join(TASK_NS + n for n in names))
        return (found.text or "").strip() if found is not None else ""

    return (
        text("Settings", "Enabled") in {"", "true"}
        and text("Actions", "Exec", "Command").lower() == command[0].lower()
        and text("Actions", "Exec", "Arguments") == windows_command_line(command[1:])
    )


class WindowsAutostart:
    """A Task Scheduler task named LapRemote, run at this user's sign-in."""

    def __init__(
        self,
        command: list[str],
        *,
        run: TaskRunner = run_schtasks,
        registry: RegistryLike | None = None,
        user: str | None = None,
        name: str = APP_NAME,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._command = command
        self._run = run
        self._registry = registry
        self._user = user
        self._name = name
        self._clock = clock
        self._cached: tuple[float, bool] | None = None

    def is_enabled(self) -> bool:
        now = self._clock()
        if self._cached is not None and now - self._cached[0] < TASK_CACHE_SECONDS:
            return self._cached[1]
        code, output = self._run(["/query", "/tn", self._name, "/xml"])
        enabled = code == 0 and task_matches(output, self._command)
        self._cached = (now, enabled)
        return enabled

    def enable(self) -> None:
        xml = task_xml(self._command, self._user or current_windows_user())
        fd, name = tempfile.mkstemp(prefix="lapremote-task-", suffix=".xml")
        path = Path(name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(xml.encode("utf-16"))
            code, output = self._run(["/create", "/tn", self._name, "/xml", str(path), "/f"])
        finally:
            path.unlink(missing_ok=True)
            self._cached = None
        if code != 0:
            msg = f"couldn't create the sign-in task: {output.strip()}"
            raise OSError(msg)
        self._remove_run_value()

    def disable(self) -> None:
        self._cached = None
        code, _output = self._run(["/query", "/tn", self._name])
        if code == 0:
            code, output = self._run(["/delete", "/tn", self._name, "/f"])
            if code != 0:
                msg = f"couldn't remove the sign-in task: {output.strip()}"
                raise OSError(msg)
        self._remove_run_value()

    def _remove_run_value(self) -> None:
        # Older versions used the Run key; left there it would start a second copy.
        if self._registry is not None:
            self._registry.delete(RUN_KEY, APP_NAME)


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
        return WindowsAutostart(command, registry=CurrentUserRegistry())
    if os_name == "macos":
        return MacAutostart(Path.home() / "Library" / "LaunchAgents", command)
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return LinuxAutostart(Path(config_home) / "autostart", command)

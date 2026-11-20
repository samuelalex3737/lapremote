"""Entry point: python -m lapremote"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
import threading
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import uvicorn

from lapremote import __version__
from lapremote.config import ConfigError, load_config
from lapremote.protocol import MAX_MESSAGE_BYTES
from lapremote.server import HTTPS_ENV, PORT_ENV
from lapremote.services import INPUT_DRY_RUN_ENV

if TYPE_CHECKING:
    from fastapi import FastAPI

    from lapremote.tray import TrayController

# Listen on every interface so phones on the same Wi-Fi can connect. Every
# message except pairing requires a device token.
BIND_HOST = "0.0.0.0"  # noqa: S104


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lapremote", description="LapRemote agent")
    parser.add_argument("--port", type=int, help="override the port from config.json")
    parser.add_argument("--dev", action="store_true", help="auto-reload on code changes")
    parser.add_argument(
        "--input-dry-run",
        action="store_true",
        help="accept input commands but never move the real mouse or type (demos and tests)",
    )
    parser.add_argument(
        "--https",
        action="store_true",
        help="serve over HTTPS with the cert and key set in config.json (see docs/HTTPS.md)",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="run without the system tray icon (headless use, servers, tests)",
    )
    parser.add_argument("--version", action="version", version=f"lapremote {__version__}")
    args = parser.parse_args(argv)
    if args.port is not None and not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    return args


def https_problem(cert: str, key: str) -> str | None:
    """Why HTTPS can't start with these files, or None when both are there."""
    if not cert or not key:
        return 'set "https": {"cert": ..., "key": ...} in config.json (see docs/HTTPS.md).'
    for label, value in (("certificate", cert), ("key", key)):
        if not Path(value).is_file():
            return f"the {label} file {value} doesn't exist."
    return None


def port_problem(port: int) -> str | None:
    """A friendly reason the port can't be used, or None when it's free."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if sys.platform == "win32":
            # Without this, Windows lets a second process bind the same port.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((BIND_HOST, port))
        except OSError:
            return (
                f"port {port} is already in use. Is LapRemote already running? "
                "Use --port to pick another one."
            )
    return None


def tray_problem(platform: str, env: Mapping[str, str]) -> str | None:
    """Why the tray icon can't be shown here, or None when it can."""
    if platform.startswith("linux") and not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        return "no desktop session"
    try:
        import pystray  # noqa: F401, PLC0415 - only checks that a tray backend loads
    except Exception as exc:
        return f"tray unavailable ({type(exc).__name__})"
    return None


def _ensure_streams() -> None:
    # A windowed (no console) build has no stdout or stderr at all.
    if sys.stdout is None:
        sys.stdout = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115 - process lifetime
    if sys.stderr is None:
        sys.stderr = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115


def _utf8_stdio() -> None:
    # The QR banner uses block characters. Piped output on Windows defaults to cp1252.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _ensure_streams()
    args = parse_args(argv)
    _utf8_stdio()
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"LapRemote could not start: {exc}", file=sys.stderr)
        return 2
    port: int = args.port if args.port is not None else config.port
    https = args.https or config.https.enabled
    ssl: dict[str, str] = {}
    if https:
        problem = https_problem(config.https.cert, config.https.key)
        if problem is not None:
            print(f"LapRemote could not start with HTTPS: {problem}", file=sys.stderr)
            return 2
        ssl = {"ssl_certfile": config.https.cert, "ssl_keyfile": config.https.key}
        os.environ[HTTPS_ENV] = "1"
    busy = None if args.dev else port_problem(port)
    if busy is not None:
        print(f"LapRemote could not start: {busy}", file=sys.stderr)
        return 2
    # The app factory runs in the (reloader) worker process, so pass the port on.
    os.environ[PORT_ENV] = str(port)
    if args.input_dry_run:
        os.environ[INPUT_DRY_RUN_ENV] = "1"
    if not args.dev and not args.no_tray:
        problem = tray_problem(sys.platform, os.environ)
        if problem is None:
            return run_with_tray(port, ssl)
        print(f"Running without a tray icon: {problem}.", file=sys.stderr)
    package_dir = Path(__file__).resolve().parent
    uvicorn.run(
        "lapremote.server:create_app",
        factory=True,
        host=BIND_HOST,
        port=port,
        reload=args.dev,
        reload_dirs=[str(package_dir)] if args.dev else None,
        reload_excludes=["static/*"] if args.dev else None,
        access_log=False,  # access logs would record ?pair= codes
        ws_max_size=MAX_MESSAGE_BYTES,
        log_level="warning",
        **ssl,  # type: ignore[arg-type]
    )
    return 0


def run_with_tray(
    port: int,
    ssl: dict[str, str],
    *,
    make_app: Callable[[], FastAPI] | None = None,
    make_icon: Callable[[TrayController], Any] | None = None,
    open_url: Callable[[str], object] = webbrowser.open,
) -> int:
    """Serve in a background thread and show the tray icon on this (main) thread."""
    from lapremote.server import create_app  # noqa: PLC0415 - heavy, only needed here
    from lapremote.tray import TrayController, build_icon  # noqa: PLC0415

    app = (make_app or create_app)()
    agent = app.state.agent
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=BIND_HOST,
            port=port,
            access_log=False,
            ws_max_size=MAX_MESSAGE_BYTES,
            log_level="warning",
            **ssl,  # type: ignore[arg-type]
        )
    )
    icon_ref: list[Any] = []

    def stop() -> None:
        server.should_exit = True
        for icon in icon_ref:
            icon.stop()

    ctl = TrayController(
        agent,
        port,
        app.state.desktop.autostart,
        stop,
        open_url=open_url,
        send_clipboard=app.state.services.clipboard.send_to_phones,
    )

    async def remember_loop() -> None:
        ctl.loop = asyncio.get_running_loop()
        if not agent.devices.list():
            # First run: open the dashboard with the welcome guide and the QR code.
            open_url(ctl.dashboard_url())

    agent.on_startup.append(remember_loop)
    thread = threading.Thread(target=server.run, name="lapremote-server", daemon=True)
    thread.start()
    icon = (make_icon or build_icon)(ctl)
    icon_ref.append(icon)

    def watch_server() -> None:
        # If the server stops on its own (port taken, crash), close the tray too.
        thread.join()
        icon.stop()

    threading.Thread(target=watch_server, name="lapremote-watch", daemon=True).start()
    icon.run()
    server.should_exit = True
    thread.join(timeout=10)
    return 0 if server.started else 1


if __name__ == "__main__":
    sys.exit(main())

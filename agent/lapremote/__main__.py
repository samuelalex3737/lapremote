"""Entry point: python -m lapremote"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from lapremote import __version__
from lapremote.config import ConfigError, load_config
from lapremote.protocol import MAX_MESSAGE_BYTES
from lapremote.server import PORT_ENV
from lapremote.services import INPUT_DRY_RUN_ENV

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
    parser.add_argument("--version", action="version", version=f"lapremote {__version__}")
    args = parser.parse_args(argv)
    if args.port is not None and not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    return args


def _utf8_stdio() -> None:
    # The QR banner uses block characters. Piped output on Windows defaults to cp1252.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    _utf8_stdio()
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"LapRemote could not start: {exc}", file=sys.stderr)
        return 2
    port: int = args.port if args.port is not None else config.port
    # The app factory runs in the (reloader) worker process, so pass the port on.
    os.environ[PORT_ENV] = str(port)
    if args.input_dry_run:
        os.environ[INPUT_DRY_RUN_ENV] = "1"
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
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

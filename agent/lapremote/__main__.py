"""Entry point: python -m lapremote"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from lapremote import __version__
from lapremote.config import ConfigError, load_config

# Phase 0 has no authentication yet, so the agent only listens on loopback.
# Phase 1 switches to 0.0.0.0 together with pairing and device tokens.
BIND_HOST = "127.0.0.1"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lapremote", description="LapRemote agent")
    parser.add_argument("--port", type=int, help="override the port from config.json")
    parser.add_argument("--dev", action="store_true", help="auto-reload on code changes")
    parser.add_argument("--version", action="version", version=f"lapremote {__version__}")
    args = parser.parse_args(argv)
    if args.port is not None and not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"LapRemote could not start: {exc}", file=sys.stderr)
        return 2
    port: int = args.port if args.port is not None else config.port
    package_dir = Path(__file__).resolve().parent
    uvicorn.run(
        "lapremote.server:create_app",
        factory=True,
        host=BIND_HOST,
        port=port,
        reload=args.dev,
        reload_dirs=[str(package_dir)] if args.dev else None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

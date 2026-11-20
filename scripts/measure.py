"""Measure a running agent: preview bandwidth and CPU, ping latency, idle CPU and memory.

1. Seed a throwaway agent home with a measurement device, then start the agent with it:
       uv run --project agent python scripts/measure.py seed C:/tmp/lr-measure
       set LAPREMOTE_HOME=C:/tmp/lr-measure
       uv run --project agent python -m lapremote --port 7795
2. Measure:
       uv run --project agent python scripts/measure.py preview --home C:/tmp/lr-measure --port 7795
       uv run --project agent python scripts/measure.py ping --home C:/tmp/lr-measure --port 7795
       uv run --project agent python scripts/measure.py idle --port 7795 [--home C:/tmp/lr-measure]
       uv run --project agent python scripts/measure.py moves --home C:/tmp/lr-measure --port 7795

Never point this at your real ~/.lapremote: `seed` refuses to touch an existing devices.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import psutil
from websockets.sync.client import ClientConnection, connect
from websockets.typing import Origin

DEVICE_ID = "measure0000000001"
PING_GAP_SECONDS = 0.005
TOKEN_FILE = "measure-token.txt"  # noqa: S105 - a file name, not a secret


def seed(home: Path) -> int:
    devices = home / "devices.json"
    if devices.exists():
        print(f"{devices} already exists; use an empty folder.", file=sys.stderr)
        return 1
    home.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    body = {
        "version": 1,
        "devices": [
            {
                "device_id": DEVICE_ID,
                "name": "Measurement",
                "platform": "other",
                "role": "owner",
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "paired_at": time.time(),
                "last_seen_at": None,
            }
        ],
    }
    devices.write_text(json.dumps(body, indent=2), encoding="utf-8")
    (home / TOKEN_FILE).write_text(token, encoding="utf-8")
    print(f"seeded {devices}")
    return 0


def agent_process(port: int) -> psutil.Process:
    for conn in psutil.net_connections(kind="tcp"):
        laddr = conn.laddr
        if conn.status != psutil.CONN_LISTEN or not conn.pid or not isinstance(laddr, tuple):
            continue
        if len(laddr) >= 2 and laddr[1] == port:
            return psutil.Process(conn.pid)
    msg = f"no process is listening on port {port}"
    raise SystemExit(msg)


class Client:
    def __init__(self, port: int, home: Path) -> None:
        token = (home / TOKEN_FILE).read_text(encoding="utf-8").strip()
        base = f"127.0.0.1:{port}"
        self.ws: ClientConnection = connect(
            f"ws://{base}/ws", origin=Origin(f"http://{base}"), max_size=None
        ).__enter__()
        self.n = 0
        self.send("auth.resume", {"deviceId": DEVICE_ID, "token": token})
        self.until("auth.ok")

    def send(self, type_: str, payload: dict[str, Any]) -> str:
        self.n += 1
        msg_id = f"m{self.n}"
        self.ws.send(json.dumps({"v": 1, "id": msg_id, "type": type_, "payload": payload}))
        return msg_id

    def until(self, type_: str, timeout: float = 10) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            raw = self.ws.recv(timeout=max(0.1, deadline - time.monotonic()))
            if isinstance(raw, str):
                msg: dict[str, Any] = json.loads(raw)
                if msg["type"] == type_:
                    return msg

    def close(self) -> None:
        self.ws.close()


def measure_preview(port: int, home: Path, seconds: float, fps: int, width: int) -> int:
    proc = agent_process(port)
    client = Client(port, home)
    client.send("preview.start", {"fps": fps, "width": width, "monitor": 0})
    proc.cpu_percent(None)
    frames = 0
    total = 0
    sizes: list[int] = []
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        raw = client.ws.recv(timeout=5)
        if isinstance(raw, bytes):
            frame = int.from_bytes(raw[:4], "big")
            frames += 1
            total += len(raw)
            sizes.append(len(raw) - 8)
            client.send("preview.ack", {"frame": frame})
    elapsed = time.monotonic() - start
    cpu = proc.cpu_percent(None)
    client.send("preview.stop", {})
    client.close()
    cores = psutil.cpu_count() or 1
    print(f"preview {fps}fps / {width}px for {elapsed:.1f}s")
    print(f"  frames received     {frames} ({frames / elapsed:.2f} fps)")
    kbps = total / elapsed / 1024
    mbit = total * 8 / elapsed / 1_000_000
    print(f"  bandwidth           {kbps:.1f} KB/s ({mbit:.2f} Mbit/s)")
    median_kb = statistics.median(sizes) / 1024
    print(f"  frame size          median {median_kb:.1f} KB, max {max(sizes) / 1024:.1f} KB")
    share = cpu / cores
    print(f"  agent CPU           {cpu:.1f}% of one core ({share:.1f}% of all {cores} cores)")
    print(f"  agent memory (RSS)  {proc.memory_info().rss / 1_048_576:.1f} MB")
    return 0


def measure_ping(port: int, home: Path, count: int) -> int:
    client = Client(port, home)
    rtts: list[float] = []
    for _ in range(count):
        sent = time.perf_counter()
        client.send("ping", {"t": sent})
        client.until("pong")
        rtts.append((time.perf_counter() - sent) * 1000)
        # Stay well under the agent's 300 messages/s limit, like a real phone.
        time.sleep(PING_GAP_SECONDS)
    client.close()
    rtts.sort()
    p50 = rtts[len(rtts) // 2]
    p95 = rtts[int(len(rtts) * 0.95) - 1]
    print(f"ping x{count}: p50 {p50:.2f} ms, p95 {p95:.2f} ms, max {rtts[-1]:.2f} ms")
    return 0


def measure_idle(port: int, seconds: float, home: Path | None) -> int:
    """Agent CPU and memory while nothing happens. With --home, a phone stays connected."""
    client = Client(port, home) if home is not None else None
    proc = agent_process(port)
    proc.cpu_percent(None)
    time.sleep(seconds)
    cpu = proc.cpu_percent(None)
    if client is not None:
        client.close()
    cores = psutil.cpu_count() or 1
    who = "phone connected" if client is not None else "no phone"
    print(
        f"idle {seconds:.0f}s ({who}): agent CPU {cpu:.2f}% of one core "
        f"({cpu / cores:.2f}% of all cores), memory {proc.memory_info().rss / 1_048_576:.1f} MB"
    )
    return 0


def measure_moves(port: int, home: Path, rate: int, seconds: float) -> int:
    """Send input.move at a trackpad-like rate, then check the agent kept up.

    Run the agent with --input-dry-run so the real cursor never moves. A ping sent right after
    the burst is answered only once every earlier move was handled, so its delay shows backlog.
    """
    client = Client(port, home)
    proc = agent_process(port)
    proc.cpu_percent(None)
    gap = 1 / rate
    sent = 0
    start = time.perf_counter()
    while time.perf_counter() - start < seconds:
        client.send("input.move", {"dx": 1.5, "dy": -0.5})
        sent += 1
        next_at = start + sent * gap
        time.sleep(max(0.0, next_at - time.perf_counter()))
    elapsed = time.perf_counter() - start
    cpu = proc.cpu_percent(None)
    probe = time.perf_counter()
    client.send("ping", {"t": probe})
    client.until("pong")
    backlog_ms = (time.perf_counter() - probe) * 1000
    client.close()
    print(f"input.move: sent {sent} in {elapsed:.1f}s ({sent / elapsed:.0f}/s)")
    print(f"  agent CPU           {cpu:.1f}% of one core")
    print(f"  ping right after    {backlog_ms:.2f} ms (low means no backlog)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure a running LapRemote agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("home", type=Path)
    p = sub.add_parser("preview")
    p.add_argument("--home", type=Path, required=True)
    p.add_argument("--port", type=int, default=7795)
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--fps", type=int, default=8)
    p.add_argument("--width", type=int, default=480)
    g = sub.add_parser("ping")
    g.add_argument("--home", type=Path, required=True)
    g.add_argument("--port", type=int, default=7795)
    g.add_argument("--count", type=int, default=500)
    m = sub.add_parser("moves")
    m.add_argument("--home", type=Path, required=True)
    m.add_argument("--port", type=int, default=7795)
    m.add_argument("--rate", type=int, default=120)
    m.add_argument("--seconds", type=float, default=10.0)
    i = sub.add_parser("idle")
    i.add_argument("--home", type=Path, help="keep a phone connected while measuring")
    i.add_argument("--port", type=int, default=7795)
    i.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if args.cmd == "seed":
        return seed(args.home)
    if args.cmd == "preview":
        return measure_preview(args.port, args.home, args.seconds, args.fps, args.width)
    if args.cmd == "ping":
        return measure_ping(args.port, args.home, args.count)
    if args.cmd == "moves":
        return measure_moves(args.port, args.home, args.rate, args.seconds)
    return measure_idle(args.port, args.seconds, args.home)


if __name__ == "__main__":
    sys.exit(main())

"""Run the agent (auto-reload) and the Vite dev server together.

    uv run --project agent python scripts/dev.py

The Vite server proxies /ws and /api to the agent. Ctrl+C stops both. If
either process exits, the other one is stopped too.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "agent"
WEB_DIR = ROOT / "web"


def require(executable: str) -> str:
    path = shutil.which(executable)
    if path is None:
        print(f"[dev] '{executable}' is not on PATH. Install it and try again.", file=sys.stderr)
        raise SystemExit(1)
    return path


def pump(prefix: str, stream: IO[str]) -> None:
    for line in stream:
        sys.stdout.write(f"{prefix} {line}")
        sys.stdout.flush()


def start(prefix: str, args: list[str], cwd: Path) -> subprocess.Popen[str]:
    # Own process group/session so the whole tree can be stopped together.
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    proc = subprocess.Popen(  # noqa: S603 - fixed executables and arguments
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
        start_new_session=sys.platform != "win32",
    )
    if proc.stdout is None:
        msg = "stdout pipe was not created"
        raise RuntimeError(msg)
    threading.Thread(target=pump, args=(prefix, proc.stdout), daemon=True).start()
    return proc


def stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        # uv -> python -> uvicorn reloader -> worker: kill the whole tree.
        taskkill = require("taskkill")
        subprocess.run(  # noqa: S603 - fixed executable, numeric pid
            [taskkill, "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    uv = require("uv")
    npm = require("npm")
    procs = [
        start("[agent]", [uv, "run", "python", "-m", "lapremote", "--dev"], AGENT_DIR),
        start("[web]  ", [npm, "run", "dev"], WEB_DIR),
    ]
    exit_code = 0
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.3)
        exited = next(p for p in procs if p.poll() is not None)
        exit_code = exited.returncode or 0
        print(f"[dev] a process exited with code {exited.returncode}, stopping the other one")
    except KeyboardInterrupt:
        print("\n[dev] stopping")
    finally:
        for proc in procs:
            stop(proc)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

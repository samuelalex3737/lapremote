"""Build the Remote web app into agent/lapremote/static/ (served by the agent).

uv run --project agent python scripts/build_web.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
OUT_DIR = ROOT / "agent" / "lapremote" / "static"


def main() -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("[build_web] npm is not on PATH. Install Node.js and try again.", file=sys.stderr)
        return 1
    if not (WEB_DIR / "node_modules").is_dir():
        code = subprocess.run([npm, "ci"], cwd=WEB_DIR, check=False).returncode  # noqa: S603
        if code != 0:
            return code
    code = subprocess.run([npm, "run", "build"], cwd=WEB_DIR, check=False).returncode  # noqa: S603
    if code != 0:
        return code
    index = OUT_DIR / "index.html"
    if not index.is_file():
        print(f"[build_web] build finished but {index} is missing", file=sys.stderr)
        return 1
    print(f"[build_web] built the Remote app into {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

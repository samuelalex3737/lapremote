"""Build the LapRemote desktop app: a one-folder PyInstaller bundle in agent/dist/LapRemote/.

uv run --project agent python scripts/build_agent.py [--skip-web]

1. Builds the Remote web app into agent/lapremote/static/ (unless --skip-web and it exists).
2. Bundles the agent with the web build, the dashboard page and shared/*.default.json
   (as lapremote/defaults/) so the app runs without the repo.

On Windows and macOS the app has no console window: pairing happens through the tray icon
and the dashboard. On Linux it keeps a console.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "agent"
PACKAGE = AGENT / "lapremote"
STATIC = PACKAGE / "static"
WORK = AGENT / "build" / "pyinstaller"
DIST = AGENT / "dist"
NAME = "LapRemote"

# Imported lazily or by name at runtime, so PyInstaller's analysis can't see them.
HIDDEN = [
    "lapremote.media.windows",
    "lapremote.media.macos",
    "lapremote.media.linux",
    "lapremote.tray",
    "lapremote.server",
]
COLLECT_SUBMODULES = ["uvicorn", "lapremote", "zeroconf"]
COLLECT_ALL_WINDOWS = ["winrt", "pycaw", "comtypes", "screen_brightness_control"]


def run(args: list[str], cwd: Path) -> int:
    print("[build_agent]", " ".join(args))
    return subprocess.run(args, cwd=cwd, check=False).returncode  # noqa: S603 - fixed tools


def build_web() -> int:
    return run([sys.executable, str(ROOT / "scripts" / "build_web.py")], ROOT)


def windows_icon() -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "lapremote.ico"
    source = STATIC / "icons" / "icon-512.png"
    with Image.open(source) as image:
        image.save(target, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return target


def pyinstaller_args() -> list[str]:
    sep = os.pathsep
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        NAME,
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK),
        "--specpath",
        str(WORK),
        "--add-data",
        f"{STATIC}{sep}lapremote/static",
        "--add-data",
        f"{PACKAGE / 'assets'}{sep}lapremote/assets",
    ]
    for default in sorted((ROOT / "shared").glob("*.default.json")):
        args += ["--add-data", f"{default}{sep}lapremote/defaults"]
    for module in HIDDEN:
        args += ["--hidden-import", module]
    for package in COLLECT_SUBMODULES:
        args += ["--collect-submodules", package]
    if sys.platform == "win32":
        for package in COLLECT_ALL_WINDOWS:
            args += ["--collect-all", package]
        args += ["--windowed", "--icon", str(windows_icon())]
    elif sys.platform == "darwin":
        args += ["--windowed"]
    args.append(str(AGENT / "packaging" / "entry.py"))
    return args


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-web", action="store_true", help="reuse the existing web build")
    args = parser.parse_args()
    if not (args.skip_web and (STATIC / "index.html").is_file()):
        code = build_web()
        if code != 0:
            return code
    code = run(pyinstaller_args(), AGENT)
    if code != 0:
        return code
    exe = DIST / NAME / (f"{NAME}.exe" if sys.platform == "win32" else NAME)
    if not exe.exists():
        print(f"[build_agent] PyInstaller finished but {exe} is missing", file=sys.stderr)
        return 1
    size = sum(f.stat().st_size for f in (DIST / NAME).rglob("*") if f.is_file())
    print(f"[build_agent] built {exe} ({size / 2**20:.0f} MB folder)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

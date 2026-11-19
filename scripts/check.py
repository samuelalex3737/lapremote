"""Run every linter, type-checker and test suite and print a summary.

    uv run --project agent python scripts/check.py            # everything
    uv run --project agent python scripts/check.py --no-e2e   # skip Playwright

Exits non-zero if any step fails.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "agent"
WEB_DIR = ROOT / "web"


@dataclass(frozen=True)
class Step:
    name: str
    args: list[str]
    cwd: Path


def resolve(executable: str) -> str:
    path = shutil.which(executable)
    if path is None:
        print(f"[check] '{executable}' is not on PATH.", file=sys.stderr)
        raise SystemExit(1)
    return path


def build_steps(include_e2e: bool) -> list[Step]:
    uv = resolve("uv")
    npm = resolve("npm")
    py = [uv, "run", "python", "-m"]
    steps = [
        Step("ruff check", [*py, "ruff", "check", ".", "../scripts"], AGENT_DIR),
        Step("ruff format", [*py, "ruff", "format", "--check", ".", "../scripts"], AGENT_DIR),
        Step("mypy --strict", [*py, "mypy"], AGENT_DIR),
        Step("pytest", [*py, "pytest"], AGENT_DIR),
        Step("eslint", [npm, "run", "lint"], WEB_DIR),
        Step("tsc --noEmit", [npm, "run", "typecheck"], WEB_DIR),
        Step("vitest", [npm, "run", "test"], WEB_DIR),
    ]
    if include_e2e:
        steps.append(Step("playwright", [npm, "run", "e2e"], WEB_DIR))
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all LapRemote checks")
    parser.add_argument("--no-e2e", action="store_true", help="skip Playwright")
    args = parser.parse_args()
    results: list[tuple[str, bool, float]] = []
    for step in build_steps(include_e2e=not args.no_e2e):
        print(f"\n===== {step.name} =====", flush=True)
        started = time.perf_counter()
        code = subprocess.run(step.args, cwd=step.cwd, check=False).returncode  # noqa: S603
        results.append((step.name, code == 0, time.perf_counter() - started))
    print("\n===== summary =====")
    for name, ok, seconds in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<14} {seconds:6.1f}s")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())

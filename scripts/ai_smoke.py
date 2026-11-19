"""Check the AI setup and try the planner against the real model, without running anything.

    uv run --project agent python scripts/ai_smoke.py check
    uv run --project agent python scripts/ai_smoke.py demo [--out docs/reports/ai-demo.log]
    uv run --project agent python scripts/ai_smoke.py ask "turn it down a bit"

`check` reports memory, the recommended Ollama model and whether the configured model is ready.
`demo` and `ask` only plan: the actions are printed and validated, never executed, so this is
safe to run on the laptop you are using. The context is a fixed sample (a Spotify session and
the default shortcuts and scenes), not your real screen.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import psutil

from lapremote.ai.planner import Planner, PlannerContext
from lapremote.ai.providers import create_provider, recommended_ollama_model
from lapremote.config import load_config
from lapremote.storage import default_file

SPEC_COMMANDS = [
    "pause everything",
    "next episode and volume 30",
    "open youtube and search lofi beats",
    "sleep the laptop in 40 minutes",
    "go back 2 minutes",
]


def sample_context() -> PlannerContext:
    shortcuts = json.loads(default_file("shortcuts.default.json").read_text(encoding="utf-8"))
    scenes = json.loads(default_file("scenes.default.json").read_text(encoding="utf-8"))
    return PlannerContext(
        media=[
            {
                "id": "spotify-1",
                "app": "Spotify",
                "title": "Midnight City",
                "artist": "M83",
                "status": "playing",
                "position": 95,
                "duration": 244,
                "canSeek": True,
            },
            {
                "id": "chrome-1",
                "app": "Chrome",
                "title": "Episode 4",
                "artist": "",
                "status": "playing",
                "position": 1210,
                "duration": 2900,
                "canSeek": True,
            },
        ],
        current_media_id="chrome-1",
        foreground={"app": "Chrome", "category": "browser", "site": "netflix"},
        volume={"level": 55, "muted": False},
        brightness=80,
        timer=None,
        shortcuts=[{"id": s["id"], "name": s["name"], "kind": s["kind"]} for s in shortcuts],
        scenes=[{"id": s["id"], "name": s["name"]} for s in scenes],
    )


async def check() -> int:
    config = load_config()
    total = psutil.virtual_memory().total
    print(f"memory: {total / 2**30:.1f} GiB usable (about {round(total / 2**30)} GB installed)")
    print(f"recommended Ollama model: {recommended_ollama_model(total)}")
    print(f"configured: provider={config.ai.provider} model={config.ai.model}")
    async with httpx.AsyncClient() as client:
        provider = create_provider(config.ai, client)
        reason = await provider.check()
    print("ready" if reason is None else f"not ready: {reason}")
    return 0 if reason is None else 1


async def plan_all(commands: list[str], out: Path | None) -> int:
    config = load_config()
    context = sample_context()
    lines: list[str] = []
    failures = 0
    async with httpx.AsyncClient() as client:
        provider = create_provider(config.ai, client)
        planner = Planner(provider)
        lines.append(f"# provider={provider.name} model={provider.model}")
        for text in commands:
            started = time.perf_counter()
            try:
                draft = await planner.plan(text, context)
            except Exception as exc:
                failures += 1
                lines.append(f"> {text}\n  FAILED: {exc}")
                continue
            ms = round((time.perf_counter() - started) * 1000)
            actions = [{"type": a.type, "payload": a.payload} for a in draft.actions]
            lines.append(f"> {text}   ({ms} ms)")
            lines.append(f"  reply: {draft.reply}")
            lines.append(f"  needsConfirm: {draft.needs_confirm}")
            lines.append(f"  actions: {json.dumps(actions)}")
            if draft.dropped:
                lines.append(f"  dropped: {draft.dropped}")
    text_out = "\n".join(lines)
    print(text_out)
    if out is not None:
        await asyncio.to_thread(out.write_text, text_out + "\n", encoding="utf-8")
        print(f"\nwritten to {out}")
    return 1 if failures else 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    demo = sub.add_parser("demo")
    demo.add_argument("--out", type=Path)
    ask = sub.add_parser("ask")
    ask.add_argument("text")
    args = parser.parse_args()
    if args.cmd == "check":
        return asyncio.run(check())
    if args.cmd == "demo":
        return asyncio.run(plan_all(SPEC_COMMANDS, args.out))
    return asyncio.run(plan_all([args.text], None))


if __name__ == "__main__":
    raise SystemExit(main())

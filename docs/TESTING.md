# Testing LapRemote

## Run everything

From the repo root:

```bash
uv run --project agent python scripts/check.py
```

Add `--no-e2e` to skip Playwright. The script prints a PASS/FAIL summary and exits non-zero if any
step fails.

## Individual tools

Agent (run inside `agent/`):

| Check | Command |
|---|---|
| Lint | `uv run python -m ruff check . ../scripts` |
| Format | `uv run python -m ruff format --check . ../scripts` |
| Types | `uv run python -m mypy` (strict, covers `lapremote`, `tests`, `../scripts`) |
| Tests | `uv run python -m pytest` |

Web (run inside `web/`):

| Check | Command |
|---|---|
| Lint | `npm run lint` (typed `strictTypeChecked` rules, zero warnings allowed) |
| Types | `npm run typecheck` |
| Unit tests | `npm run test` (vitest) |
| Mobile smoke tests | `npm run e2e` (Playwright, iPhone 15 on WebKit and Pixel 8 on Chromium) |

First-time Playwright setup: `npx playwright install chromium webkit`.

## Notes

- **Use `python -m <tool>`, not the `.exe` shims.** On this Windows 11 machine Smart App Control
  blocks the unsigned launcher executables uv creates in `.venv\Scripts` (`pytest.exe` fails with
  "An Application Control policy has blocked this file"). Running the tools as modules avoids it.
- **Isolation.** Every pytest test gets its own `LAPREMOTE_HOME` in a temp folder, so the real
  `~/.lapremote` is never touched. The Playwright run starts its own agent on port 7787 with a temp
  `LAPREMOTE_HOME` and its own Vite server on 5183, so it never collides with a running agent.
- **Screenshots.** Playwright saves `<project>-home.png` for each device under
  `web/test-results/` (git-ignored). The HTML report is in `web/playwright-report/`.

## What is covered (Phase 0)

| Area | Tests |
|---|---|
| Config | defaults match the spec exactly, first-run file creation, round trip, partial files, unknown keys, broken JSON kept intact, out-of-range values, atomic writes |
| Platform detection | OS mapping, unsupported OS, Linux display server (X11 / Wayland), media CLI lookup, real host detection |
| Server | `/api/health` body, docs endpoints disabled, 404 and 405 handling |
| Entry point | port from config, `--port` override and range check, `--dev` reload, friendly exit on a broken config |
| Web | health response parsing and fetch errors (vitest), agent found through the dev proxy, no horizontal scroll, offline message and retry, 44px tap target (Playwright) |

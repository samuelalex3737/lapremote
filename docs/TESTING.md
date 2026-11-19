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
  `LAPREMOTE_HOME` (seeded with one paired test device, see `web/tests/e2e/seed.ts`) and its own
  Vite server on 5183, so it never collides with a running agent.
- **Protocol schema.** After changing `protocol.py`, run `uv run python -m lapremote.protocol --write`
  (inside `agent/`) and update `protocol.ts` until the vitest sync test passes.
- **Screenshots.** Playwright saves `<project>-home.png` for each device under
  `web/test-results/` (git-ignored). The HTML report is in `web/playwright-report/`.

## What is covered

| Area | Tests |
|---|---|
| Config | defaults match the spec exactly, first-run file creation, round trip, partial files, unknown keys, broken JSON kept intact, out-of-range values, atomic writes |
| Platform detection | OS mapping, unsupported OS, Linux display server (X11 / Wayland), media CLI lookup, real host detection |
| Server | `/api/health` body, docs endpoints disabled, 404 and 405 handling |
| Entry point | port from config, `--port` override and range check, `--dev` reload, friendly exit on a broken config |
| Protocol sync | PROTOCOL.md type lists vs `protocol.py` and `protocol.ts`; every payload's fields, required-ness, nullability and enums vs `shared/protocol.schema.json` (pytest + vitest) |
| Pairing and devices | one-time codes (expiry, reuse, rotation), token hashing, owner/guest rules, last-owner protection, persistence |
| WebSocket | pair, resume, bad token, expired and reused codes, auth timeout (4001), Origin check (4003), role denial, malformed JSON/envelope/payload, unknown types, binary frames, pairing/general/key.text rate limits, revoke closes the socket, role changes, logs never hold tokens, codes or typed text |
| Real socket | a tiny Python client pairs, resumes and pings a live uvicorn agent; wrong Origin gets HTTP 403 |
| Network | LAN IP choice skips WSL, VirtualBox, Docker and VPN adapters |
| Web | WS client (pairing, resume, backoff 0.5-5s, offline queue, acks, timeouts, latency, revoke), credentials storage, device naming (vitest); resume over a real socket, wrong code from the QR link, code input rules, unpaired token (Playwright, iPhone 15 + Pixel 8) |

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
| Input (agent) | sub-pixel carry, click/drag/lock release, per-OS scroll units and direction, combos release modifiers on failure, zoom keys, allowlist, permission matrix (macOS Accessibility, Wayland), DPI awareness, guest move-only, buttons released on disconnect and revoke, dry run |
| Gestures (web) | every rule in the Phase 2 table with synthetic pointer sequences, plus edge cases (7px is not a tap, 180ms is not a tap, pinch plus drift does not scroll, leftover finger after scroll, cancel mid-drag), the coalescing sender, combos, settings, haptics |
| Trackpad (e2e) | a real tap produces `input.click`; Chromium touch events produce moves and two-finger scrolls on the agent (read from the dry-run log); settings persist |
| Media (agent) | smart-seek decision table, interpolation, context classification, app names, thumbnails and artwork ids, macOS stream parsing (full + diff), playerctl parsing, volume parsers, media.state with artwork once per connection, media.artwork, commands per session, unresponsive players, media keys fallback, API and key seek (browser only), drift suppression, volume over the socket, volume poll, volume key fallback, and a read-only test against the real Windows media sessions |
| Media (web) | interpolation (stays within 1s over 5 minutes), time formatting, artwork cache, current session; the e2e media panel reads the laptop's real sessions and volume (read-only) |
| App shell (e2e) | each of the 5 tabs on iPhone 15 and Pixel 8: screenshot, no horizontal scroll, every target at least 44x44, axe-core WCAG 2.1 AA with no serious or critical issues; More sub-screens; pairing screen checks; swipe navigation (not on the trackpad); offline splash; reduced motion; landscape trackpad; manifest, icons and iOS meta |
| Lighthouse | `npm run lighthouse -- http://127.0.0.1:<port>/` against an agent serving the built app (mobile emulation) |
| Adaptive (web) | mode suggestions for every category and site, movie keys per site, colour maths (accent always at least 4.5:1), scrubber maths |
| Now Playing (e2e, scripted agent) | Netflix banner, then Switch, then movie controls (skip intro `s`, fullscreen `f`, no subtitles); focus change swaps the banner (measured 260ms Chromium and 610ms WebKit alone); dismiss sticks; slides mode keys and timer; accent from artwork; position interpolates; drag-to-seek (Chromium) and keyboard seek (WebKit); swipe artwork for next; auto-switch |
| Preview (agent) | output sizing, big-endian header, JPEG encoding, backpressure over a socket (stops at 2 unacked frames, resumes on ack), unknown monitor, feature gating, absolute-click mapping on 5 layouts including a negative origin, calibration page, real capture on Windows |
| Preview (web) | header parsing, letterbox mapping, zoom and pan undo, clamping; e2e: frames acked, centre tap gives (0.5, 0.5), letterbox taps ignored, stop on leave, hold for right click (Chromium), monitor picker restarts the stream, the real agent streams the screen and taps reach the input engine |
| Measurements | `uv run --project agent python scripts/measure.py preview\|ping\|idle` against a seeded throwaway agent; `npm run tap-accuracy -- <port> <deviceId> <token>` (real clicks, agent without dry run) |
| Phase 7 (agent) | seeded defaults and broken-file recovery, shortcut store, app path validation on all three OSes, launcher over the socket, owner-only rules, scene runner order and partial failure, scenes over the socket (volume, brightness and launch really applied to fakes), end-of-media maths, fade levels, fade, pause, restore and lock, cancel mid-fade restores volume, timer over the socket, power token expiry, reuse and wrong action, power over the socket, brightness, real brightness read |
| Phase 7 (web) | live typing diff, OS shortcuts, timer maths, URL normalising and id slugs; e2e: keys, launch (open, add, open once, delete), scenes (run, build), timer (preset, countdown, cancel, end of track), power (hold to confirm, early release does nothing), brightness, quick launch |
| Web | WS client (pairing, resume, backoff 0.5-5s, offline queue, acks, timeouts, latency, revoke), credentials storage, device naming (vitest); resume over a real socket, wrong code from the QR link, code input rules, unpaired token (Playwright, iPhone 15 + Pixel 8) |

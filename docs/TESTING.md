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
| Phase 8 (agent) | allowlist and payload validation (unknown types, bad values, unknown ids, flat payloads, caps), power without token, confirmation rules, prompt contents (every action, ids, no window title), retry on malformed JSON and on invalid steps, worse retry keeps the first answer, provider errors; Ollama, Groq and Gemini request shapes with a mock transport (Gemini key in header), provider choice from config and env, model by RAM; over the socket: the 5 spec examples planned and executed against fakes, power waits for confirm, decline, device-bound confirm, partial failure, slow planning doesn't block other messages, feature status, guests refused; `--https` arguments and secure context |
| Phase 8 (web) | action labels, suggestion chips, air mouse mapping (dead zone, direction, smoothing, long gaps); e2e: AI unavailable reason, ask by chip and text with step chips, confirm and cancel, mic and air mouse on a secure page (motion only while holding), HTTPS help on http |
| Live AI | `scripts/ai_smoke.py demo` plans the 5 spec commands with the real model and prints the actions without running them |
| Phase 9 (agent) | pause over the socket (control refused, ping and pong still work, toasts, saved flag), dashboard access (other machine, rebinding Host, CSP nonce, no framing), writes need the header and a local Origin, dashboard state (QR, URL, checklist, handling times, first run), revoke and role rules, autostart and settings (validation, unknown fields refused), Windows Run command quoting, macOS plist, Linux desktop entry, a real registry round trip on a scratch key, tray menu actions, tray mode serving from a thread with a fake icon |
| Phase 10 (agent) | no polling without phones and a fresh read on connect, resume after an agent restart, broken `devices.json` fails closed, busy port message, a vanishing volume device doesn't break the socket |
| After v1.0.0 (agent) | volume indicator order, top-of-range, muted, debounce, late key presses (the bug found on the real laptop), mute by key; Store app ids from paths; app shortcuts by id; site icon safety (LAN, loopback, redirects, size caps, SVG, re-encoding, big pages, refusing sites); clipboard and links (owner-only, never logged); upload (names, no overwrite, auth, origin, size); layouts (defaults per OS, save, normalise, bad actions refused, broken file); laptops (sightings, MAC, magic packet, remember, wake, health checks); default layouts kept in sync with the phone's tests |
| After v1.0.0 (Wi-Fi address) | remembered address, broken file, offline keeps the last one, one report per change, failing listeners, failed checks; a change while running updates the pairing link and the dashboard note; tray mode opens the code after moving networks, and not on the same network or with no phones |
| After v1.0.0 (web) | two-finger scroll vs pinch (fails on the old rule), layout matching and messages, lock-screen mapping and WAV, links, light-mode contrast; e2e: light mode, send to laptop, pushed clipboard, call buttons, layout editor, laptops, launcher icons and app picker, lock screen; every screen at 7 sizes |
| Phase 7 (web) | live typing diff, OS shortcuts, timer maths, URL normalising and id slugs; e2e: keys, launch (open, add, open once, delete), scenes (run, build), timer (preset, countdown, cancel, end of track), power (hold to confirm, early release does nothing), brightness, quick launch |
| Web | WS client (pairing, resume, backoff 0.5-5s, offline queue, acks, timeouts, latency, revoke), credentials storage, device naming (vitest); resume over a real socket, wrong code from the QR link, code input rules, unpaired token (Playwright, iPhone 15 + Pixel 8) |

## Measurements (v1.0.0, development laptop, localhost)

Run against a throwaway agent started with `--input-dry-run` (see `scripts/measure.py`).

| Measure | Result |
|---|---|
| Ping round trip, 500 pings | p50 0.64 ms, p95 1.02 ms, max 172 ms (one outlier) |
| `input.move` at 120/s for 10 s | all handled, agent 7.3% of one core, ping right after 0.74 ms (no backlog) |
| `input.move` at 240/s for 10 s | all handled, agent 13.6% of one core, ping right after 0.78 ms |
| Idle, no phone connected | 0.7% of one core, 97 MB |
| Idle, phone connected | 4.8% of one core (0.4% of all 12 cores), 97 MB |
| Screen preview 8 fps / 480 px | 7.87 fps, 87 KB/s (0.72 Mbit/s), agent 21.6% of one core, 113 MB |
| Lighthouse (mobile, agent-served build) | performance 99, accessibility 100, best practices 100, SEO 63 (`robots.txt` disallows crawling on purpose) |

Wi-Fi latency needs a real phone: the phone shows its round trip in the status bar.

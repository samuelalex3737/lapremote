# Changelog

All notable changes to LapRemote. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Phase 6 - Live screen preview and tap-to-click

- Agent preview:
  - mss capture on one dedicated thread
  - native BGRX decode, integer box reduce, JPEG at the configured quality
  - 8-byte big-endian frame header (frame, monitor)
  - per-connection streams at the requested fps and width, never more than 2 unacked frames (capture is skipped while the phone is behind)
  - stops on preview.stop or disconnect
- `preview.meta` with the output size and every monitor's physical geometry.
- `input.absclick` maps normalised coordinates to the chosen monitor's physical pixels
  (offsets and DPI included), moves the cursor and clicks.
- `/calibration` page with five targets that measure click error in physical pixels.
- Web Screen view (Trackpad tab, "Trackpad | Screen"):
  - live frames, acked once drawn, monitor picker
  - local pinch-zoom and pan, a Fit button
  - tap to click, hold to right-click, with a ripple
  - stops when hidden or unmounted, restarts after a reconnect
- `scripts/measure.py` (preview bandwidth and CPU, ping latency, idle CPU) and
  `npm run tap-accuracy` (end-to-end click accuracy on the real screen).

### Phase 5 - Now Playing and adaptive context

- Agent context engine: the foreground app on Windows (pywin32), macOS (NSWorkspace + Quartz)
  and Linux X11 (xdotool), classified into browser, music, video, presentation, desktop or
  other, with the site detected from browser titles (YouTube, Netflix, Prime Video, Spotify).
  Polled every 500ms and pushed as `context.state` only on change.
- Now Playing:
  - large artwork with a soft glow, and a background gradient from the artwork colour (fast-average-color) cross-fading over 600ms
  - an app-wide accent colour that always keeps 4.5:1 contrast
  - app badge, live interpolated scrubber with drag-to-seek (with time preview) and keyboard seek
  - -10s / play-pause / +10s, previous/next, swipe the artwork for next/previous
  - session chips, volume, and "Nothing playing"
- Adaptive UI: a banner such as "Netflix in focus - movie controls" with a one-tap switch and
  dismiss. Auto-switch is a setting (off by default).
- Movie mode: huge play/pause, -10s/+10s, fullscreen (f), skip intro (Netflix s, hidden
  elsewhere) and subtitles (YouTube c, hidden elsewhere). Music mode: artwork first.
  Presentation mode: big next/previous, blank screen (b) and an elapsed talk timer.
- e2e tests drive the UI through a scripted stand-in agent (`page.routeWebSocket`), so they
  don't depend on what is playing on the laptop.

### Phase 4 - Remote app shell and design system

- Design tokens in Tailwind v4 `@theme`: layered dark backgrounds, glass surfaces, text tiers with
  AA contrast, a dynamic accent, status colours, 24px card radius, pills, and spring presets
  (snappy, gentle).
- Components: Button, IconButton, HoldButton (hold-to-confirm with a progress ring), Slider
  (big target, haptic tick every 10%), SegmentedControl, Sheet (draggable bottom sheet), Toast,
  StatusPill, Card, Switch, ListRow, EmptyState, Skeleton and Logo.
- Navigation: a bottom tab bar (Now Playing, Trackpad, Keys, Launch, More) with an animated
  indicator, plus swipe between tabs (not on the trackpad). More holds Scenes, Timer, Power, AI,
  Devices and Settings. Features the laptop doesn't offer show the agent's own reason.
- Connection UX: splash, pairing, then the app. A status pill shows "Connected to <host> · 12ms".
  An offline banner shows while reconnecting, and an offline splash with "Try now" appears when
  the first connection fails.
- Keys tab (type text, quick keys, arrows) and Settings (laptop info, trackpad settings, forget
  laptop).
- State in Zustand (UI, connection mirror, media mirror, trackpad settings).
- PWA: manifest, original logo mark, icons (192, 512, maskable, apple-touch), 7 iOS splash
  screens, iOS meta tags, service worker (registers on HTTPS or localhost), self-hosted Inter
  font (no internet needed) and robots.txt (never indexed).
- Reduced motion, safe areas, 44px targets, a landscape trackpad layout, and touch-action pan-y
  on scrolling content so horizontal swipes reach the app.
- Agent: correct MIME types for .webmanifest, .js and .woff2 on Windows.
- `npm run lighthouse` audits the built app through the Lighthouse Node API.

### Phase 3 - Universal media engine

- `MediaBackend` ABC with an async change stream. Backends:
  - Windows GSMTC: sessions, metadata, artwork thumbnails, playback and timeline events, per-session control and seek
  - macOS `media-control stream`
  - Linux `playerctl --follow`
  - OS media keys fallback
- `media.state` pushed on change with artwork sent once per connection (`artworkId`).
  `media.artwork` serves images a phone is missing. Position-only updates are suppressed unless
  they drift more than 1 second from interpolation.
- Smart seek: the session API when the player can seek, otherwise site keys (YouTube j/l,
  Netflix/Prime arrows, generic arrows), and only when a browser is in front.
- Volume per OS (pycaw / osascript / pactl), polled every 500ms and pushed only on change, with a
  volume-key fallback.
- Foreground app detection and classification (browser sites, music, video, presentation) on
  Windows, used by smart seek.
- COM runs multithreaded so pycaw and WinRT share the asyncio thread without deadlocks.
- One failing feature can no longer stop the others from sending their state on connect.
- Web: media store with an artwork cache and position interpolation. A media screen lists every
  session with prev, -10s, play/pause, +10s and next, plus volume.

### Phase 2 - Input engine and trackpad

- Agent `input/`: relative moves with sub-pixel carry, clicks, press/release (drag), per-OS
  high-resolution scroll, zoom (Ctrl/Cmd + =/-), allowlisted key combos and text (typed off the
  event loop). Held buttons are released when a phone disconnects or is revoked.
- Windows: per-monitor DPI awareness at startup, so coordinates are physical pixels.
- macOS: missing Accessibility permission is detected and sent to the owner as a toast with exact
  steps. Linux: Wayland is reported as unsupported for input, with the fix.
- `--input-dry-run` flag: accept input but log it instead of moving the real mouse (used by e2e
  tests and demos).
- Web gesture engine (`lib/gestures/`): pure, unit-tested state machine for move with acceleration,
  tap, tap-then-drag, long-press drag lock, two-finger tap, two-finger scroll with inertia, pinch
  zoom (8%, re-baselined, 120ms debounce), three-finger swipes and the right-edge scroll strip.
  Moves and scrolls are coalesced to one message per animation frame, with the remainder carried.
- Trackpad screen: touch-action none, Safari gesture blocking, left/right buttons, gesture hints
  until the first touch, and settings (speed, acceleration, scroll speed, natural scroll,
  tap-to-click, three-finger mappings) saved on the phone. Haptics on Android, a silent no-op on
  iOS.
- Toasts for agent messages and failed requests.

### Phase 1 - Agent core, pairing and security

- Agent listens on `0.0.0.0:7777`, serves the built Remote app (SPA fallback, cache headers) and the
  `/ws` WebSocket.
- Pairing: one-time 6-digit code (5 minutes, single use, auto-rotates) printed as a terminal QR code
  for `http://<lan-ip>:7777/?pair=<code>`. LAN IP picked from the default route, skipping virtual
  adapters.
- Devices: 32-byte tokens returned once, only SHA-256 hashes stored in `devices.json`. First device
  is the owner, later ones are guests. Owners can promote, demote and revoke (revoked sockets close
  with 4003). The last owner can't be removed.
- Router: full role table, pydantic validation, friendly `ack ok:false` on any bad input, the
  socket is never closed for it. Auth required within 5 seconds (4001). `Origin` must match the host.
- Rate limits: pairing 5/min/IP, 300 messages/s per connection, `key.text` 10/s.
- `protocol.py` with every message (spec + approved additions), and a normalised schema export
  in `shared/protocol.schema.json`.
- Web: `protocol.ts` zod mirror with sync tests against PROTOCOL.md and the schema. WebSocket
  client with pairing, resume, 0.5-5s backoff, offline queue and latency pings. Pairing screen
  with friendly errors. Devices screen for owners.
- mDNS: `_lapremote._tcp` and `lapremote.local`. zeroconf is built in its pure-Python mode
  because Smart App Control blocks its compiled extension.
- JSON-lines command log in `~/.lapremote/logs/agent.log` (5 x 1MB). Tokens, codes and typed text
  are never logged. Access logs are off because they would record `?pair=` codes.
- `GET /api/health` now returns only `{ok, version, uptime}`.
- `scripts/build_web.py` builds the Remote app into `agent/lapremote/static/`.

### Phase 0 - Recon and scaffold

- Agent package (`python -m lapremote`) on Python 3.12, managed by uv with a committed `uv.lock`.
- `config.py`: `~/.lapremote/config.json` with the spec defaults, validation, atomic saves, and a
  friendly error instead of overwriting a broken file.
- `system/platform_info.py`: OS, version, media CLI (`media-control` / `playerctl`) and Linux display
  server detection.
- `server.py`: FastAPI app factory with `GET /api/health`. Listens on 127.0.0.1 only until pairing
  lands in Phase 1.
- Remote web app scaffold: Vite 8, React 19, TypeScript 6 (strict), Tailwind CSS 4, zod. Health check
  screen with an offline state and retry.
- Tooling: ruff, mypy `--strict`, pytest, eslint (`strictTypeChecked`), tsc, vitest, Playwright
  (iPhone 15 + Pixel 8).
- Scripts: `dev.py` (agent with auto-reload + Vite with `/api` and `/ws` proxy), `check.py` (all
  checks with a summary), `recon.py` (host report).
- Docs: architecture (Mermaid), protocol (spec verbatim, clarifications, canonical message list,
  open questions), platform matrix, testing.

# Changelog

All notable changes to LapRemote. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### New features

- **Send to laptop and back** (More > Send to laptop): put text on the laptop clipboard, open a
  link in the laptop's browser, pull the laptop's clipboard to the phone, and send photos or files
  (saved in Downloads\LapRemote, up to 100 MB). The tray and the dashboard can send the laptop's
  clipboard to the phone.
- **Video call buttons**: Zoom, Microsoft Teams and Google Meet layouts (mute, camera, share,
  raise hand, chat, leave). When a call app is in front, the header offers them.
- **Per-app layouts** (Keys > Buttons, More > Layouts): your own buttons per app, shown
  automatically for the app in front. VLC, Spotify and YouTube layouts are included.
- **Lock-screen controls**: play, pause, skip and seek from the phone's lock screen, with the
  title and artwork (Settings > Controls on the lock screen).
- **Several laptops** (More > Laptops): other LapRemote laptops on the Wi-Fi, with Open, and
  **Wake** for one that's asleep (Wake-on-LAN).
- **Real icons** for your shortcuts: the website's own icon or the app's Windows icon.
- **App picker**: add an app shortcut by picking from the laptop's installed apps.
- **Light mode**: dark stays the default; the sun and moon button at the top switches.

### Fixes

- Two-finger scrolling no longer turns into zoom when the fingers start close together.
- Changing the volume from the phone now shows the laptop's own volume indicator.
- Microsoft Store apps (such as Spotify) open from shortcuts; old shortcuts to their .exe are
  fixed on first use.
- The phone's lock-screen code can no longer crash the app on browsers without MediaMetadata.
- Two laptops with the same computer name no longer hide each other on the network.

### Windows Smart App Control

- The agent's environment now prefers an installed, signed Python (`python-preference = "system"`):
  Smart App Control started blocking a DLL in uv's downloaded Python build. README explains the fix.

### Fits any screen

- Every main screen (Now Playing in all three modes, Trackpad, Keys, Launch, More, Power, Timer,
  Scenes, Ask LapRemote) fits without scrolling on a small phone (360 x 600), an iPhone in Safari
  (393 x 659), a phone in Chrome (390 x 720), a big phone (430 x 860), a tablet (768 x 1024) and
  phones held sideways (780 x 360 and 640 x 320). A Playwright test checks all 7 sizes on iPhone 15
  and Pixel 8 emulation.
- Held sideways, the tab bar becomes a side rail and screens switch to two or three columns
  (artwork beside controls, keys in three groups, five launcher tiles per row, power buttons
  beside brightness). Short screens get tighter spacing; tablets center the app.
- One header row: the connection status, or a status dot plus the "in focus" suggestion. The
  "Can't reach your laptop" message lives in the status pill instead of a separate bar.
- Now Playing: the artwork takes only the space that's left; smaller title, play button and
  volume card.
- Keys: inline Send button, arrows on one row, compact combo builder.
- Launch: three columns of shorter tiles (labels wrap to two lines); power buttons slightly smaller;
  slimmer tab bar.

## [1.0.0] - 2026-11-20

First complete release. Tested on Windows 11; macOS and Linux are implemented but untested (see
docs/PLATFORM_MATRIX.md). Real-phone checks are listed in each phase report.

### Phase 10 - Hardening, measurements and docs

- Idle cost: volume, foreground-app and brightness polling pause while no phone is connected, and a
  phone gets a fresh read when it connects. Idle CPU with no phone went from 4.0% to 0.7% of one core.
- Phone app split into chunks: the tabs other than Now Playing load on demand and are prefetched
  when the app is idle; libraries get their own cacheable chunks. Largest chunk 211 kB (was 604 kB).
- A busy port gives a clear message ("port 7777 is already in use. Is LapRemote already running?").
- A broken `devices.json` is moved aside and the agent starts with no devices (fails closed).
- `scripts/measure.py`: `moves` (input rate and backlog) and `idle --home` (with a phone connected).
- SECURITY.md: threat model, audited list of every program the agent can start, residual risks.
- Full README (install, run and pair, HTTPS, AI, troubleshooting, roadmap) and docs/DEMO_SCRIPT.md.
- Measurements recorded in docs/TESTING.md.

### Phase 9 - Tray, desktop dashboard, start at login and packaging

- Tray icon (pystray) with Pair a phone, Devices, Pause remote control, Open dashboard, Start at
  login, Open logs folder and Quit. The server runs in a background thread; `--no-tray` keeps the
  old terminal-only mode, which is also used automatically when there's no desktop session.
- `/desktop` dashboard, only for the laptop itself: pairing QR with a New code button, devices
  with online status and the laptop's handling time (median / 95th percentile), make owner or
  guest, remove, a permission checklist built from the feature status, and settings (browser,
  AI provider and model, preview quality).
- Pause remote control: phones stay connected but every control message is refused with a clear
  message, and phones get a toast when it changes. Saved in `config.json`.
- Start at login on Windows (Run key), macOS (LaunchAgent) and Linux (XDG autostart).
- First run: the dashboard opens with a short pairing guide while no phone is paired.
- `scripts/build_agent.py` builds a one-folder PyInstaller app with the web build, the dashboard
  and the default shortcuts and scenes inside.
- Tests no longer leak `LAPREMOTE_PORT` / `LAPREMOTE_HTTPS` between test cases.

### Phase 8 - AI commands and secure-context features

- AI assistant (More > Ask LapRemote):
  - providers: Ollama on the laptop (default, `qwen2.5:7b` on 16 GB or more, `qwen2.5:3b` below),
    plus optional Groq and Gemini free tiers with keys from environment variables
  - the system prompt is generated from the protocol's action allowlist plus a short laptop summary
    (players, foreground app, volume, brightness, timer, shortcut and scene ids)
  - strict `{reply, actions}` JSON: unknown actions and bad payloads are dropped and counted in the
    reply; one retry with the exact reasons when the answer is broken or has bad steps
  - power actions, long typing and app launches wait for a confirm sheet on the phone
  - steps run in order through the same services as the buttons; `ai.result` reports each step
  - planning runs beside the phone's other messages, so the trackpad stays responsive
  - phone: chat, suggestion chips that fit the laptop right now, step chips with done or failed marks
- `--https` serves the agent over TLS with the cert and key from `config.json`. `docs/HTTPS.md`
  covers mkcert and Tailscale Serve.
- Voice input with Web Speech on secure pages, and a keyboard-dictation hint elsewhere.
- Gyro air mouse (secure pages): point the phone to move the cursor while holding the clutch, with
  a dead zone, smoothing and a speed setting. On plain http it explains how to get HTTPS.
- Protocol clarification 11 (AI plans). No message changes.
- `scripts/ai_smoke.py` checks the AI setup and plans sample commands without executing them.

### Phase 7 - Keyboard, launcher, scenes, timer, power

- Keys tab:
  - Send or Live typing; Live sends a diff, so backspace works too
  - quick keys including OS-aware Start, Spotlight or Activities, and arrows
  - common shortcuts with Cmd on macOS, and a combo builder (modifiers, then a key)
- Launcher:
  - `~/.lapremote/shortcuts.json` seeded with Netflix, YouTube, YouTube Music, Prime Video and Spotify
  - URLs (http/https only) open in the preferred browser, Brave first
  - apps open only from validated, stored paths or bundle ids, never with arguments
  - add, edit, reorder and delete from the phone; "Open a website" sheet with Open once or Save and open
- Scenes: `~/.lapremote/scenes.json` seeded with Movie Night and Focus Music. Steps run in the
  background with a toast at the end naming any failed step. Editor on the phone.
- Sleep timer:
  - presets of 15/30/45/60/90 minutes, or the end of the current track (disabled when the length is unknown)
  - pause, pause + lock or pause + sleep at the end
  - the volume fades over the last 30 seconds and is restored after pausing
  - live countdown on Now Playing
- Power: lock, sleep, restart and shut down. Hold to confirm (1.2s) on the phone plus a
  single-use, action-bound token from the agent that is valid for 10 seconds.
- Brightness: get, set and push (screen-brightness-control). Reported as unsupported on macOS.
- Agent `Actions` facade shared by scenes, the timer and (next) the AI planner. Service wiring
  moved to `services.py`.
- "Nothing playing" shows quick-launch shortcuts.

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

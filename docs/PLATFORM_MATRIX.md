# Platform matrix

Legend: **Tested** = run and verified on that OS. **Implemented-untested** = code exists but has
not been run on that OS. **Unsupported** = will not work, with the reason.

Everything marked Tested was run on the development host: Windows 11 Home Single Language, build 26300, one 1920x1080 display at
125% scaling, Python 3.12.16, Node 26.13.0.

| Feature | Phase | Windows | macOS | Linux |
|---|---|---|---|---|
| Agent starts, `GET /api/health` | 0 | Tested | Implemented-untested | Implemented-untested |
| Config load/save (`~/.lapremote/config.json`) | 0 | Tested | Implemented-untested | Implemented-untested |
| OS and media CLI detection | 0 | Tested | Implemented-untested | Implemented-untested |
| Linux display server detection (X11 / Wayland) | 0 | n/a | n/a | Implemented-untested (unit tested with simulated environments) |
| Recon script (displays, DPI scale) | 0 | Tested | Implemented-untested, scale shows "not detected" | Implemented-untested, scale shows "not detected" |
| Dev script (agent + Vite) | 0 | Tested | Implemented-untested | Implemented-untested |
| WebSocket server on 0.0.0.0, static Remote app | 1 | Tested | Implemented-untested | Implemented-untested |
| Pairing QR + code in terminal, LAN IP choice | 1 | Tested (picked the Wi-Fi adapter) | Implemented-untested | Implemented-untested |
| Pairing, resume, roles, revoke, rate limits, Origin check | 1 | Tested (pytest + real socket) | Implemented-untested | Implemented-untested |
| mDNS `_lapremote._tcp` + `lapremote.local` | 1 | Tested (browsed with zeroconf on this host) | Implemented-untested | Implemented-untested |
| JSON-lines log, 5 x 1MB rotation | 1 | Tested | Implemented-untested | Implemented-untested |
| Remote: pair / resume / reconnect / devices screen | 1 | Tested in Playwright: iPhone 15 (WebKit), Pixel 8 (Chromium). Real phone: pending Sam's check | same | same |
| Mouse move / click / drag / scroll / zoom (pynput) | 2 | Tested (real cursor moved 41px and back; DPI per-monitor, 1920x1080 physical) | Implemented-untested (needs Accessibility, detected with AXIsProcessTrusted) | Implemented-untested on X11. Unsupported on Wayland (reported with fix) |
| High-resolution scroll | 2 | Implemented (1/120 notch SendInput), not checked by hand yet | Quarter-notch pixel scroll, untested | Whole notches only (X11 limitation) |
| Key combos and text (`key.press`, `key.text`) | 2 | Tested via dry run and unit tests; real typing not run in tests | Implemented-untested | Implemented-untested |
| Gesture trackpad (all gestures) | 2 | Gesture engine unit-tested. Tap, drag and two-finger scroll proven end to end in Playwright (dry run). Real phone: pending Sam's check | same | same |
| Three-finger shortcuts | 2 | Win+Tab, Win+D, Ctrl+(Shift+)Tab | Ctrl+Up, F11, Ctrl+(Shift+)Tab, untested | Super+S, Super+D (desktop dependent), untested |
| Media sessions (list, metadata, artwork, status, timeline) | 3 | Tested (GSMTC: real Spotify session read through the agent, artwork 4.7 KB JPEG) | Implemented-untested (`media-control stream`; needs macOS 15.4+ and `brew install media-control`) | Implemented-untested (`playerctl --follow`; only `file://` artwork is read) |
| Play/pause/next/prev per session | 3 | Tested (pause on a paused Spotify session acked; full play/next pending Sam) | Implemented-untested (single now-playing session) | Implemented-untested |
| Seek via API | 3 | Tested (seek to the same position acked by Spotify) | Implemented-untested | Implemented-untested |
| Smart seek with site keys (YouTube j/l, Netflix/Prime arrows, generic arrows) | 3 | Decision table unit-tested; foreground check uses pywin32. Real sites pending Sam | Unsupported until Phase 5 adds macOS foreground detection (refuses safely) | Unsupported until Phase 5 adds X11 foreground detection (refuses safely) |
| Media keys fallback | 3 | Unit-tested through the router | Implemented-untested | Implemented-untested |
| Volume get/set/step/mute + 500ms push | 3 | Tested (pycaw read 100% muted through the agent; set only in unit tests to avoid changing Sam's volume) | Implemented-untested (osascript) | Implemented-untested (pactl) |
| App shell: tab bar, swipe tabs, Splash, offline banner, toasts, sheets | 4 | Tested in Playwright (iPhone 15 WebKit, Pixel 8 Chromium); swipe tested on Chromium touch | same | same |
| PWA manifest, icons, iOS splash screens and meta tags | 4 | Manifest, icons and meta checked in Playwright; Add to Home Screen on a real iPhone pending Sam | same | same |
| Service worker (offline shell) | 4 | Built and served; browsers only register it on HTTPS or localhost, so on plain LAN http it is skipped (HTTPS comes in Phase 8) | same | same |
| Context engine (foreground app, category, site, 500ms push on change) | 5 | Tested (real: Chrome reported as browser/generic through the agent; real foreground read in pytest) | Implemented-untested (NSWorkspace + Quartz window list; titles need Screen Recording permission) | Implemented-untested on X11 (xdotool). Unsupported on Wayland (reported) |
| Smart seek foreground check | 5 | Tested (Windows) | Implemented-untested (now uses the macOS reader) | Implemented-untested (X11) |
| Now Playing (artwork glow, colour theme, scrubber, swipe, chips) | 5 | Tested in Playwright with a scripted agent; real sessions shown in Phase 4 screenshots | same | same |
| Context banner, movie / music / slides modes, auto-switch | 5 | Tested in Playwright with a scripted agent; real focus switching pending Sam | same | same |
| Screen preview (mss, JPEG, at most 2 frames in flight) | 6 | Tested: 7.75 fps at 8fps/480px, 108 KB/s, agent 16.8% of one core | Implemented-untested (needs Screen Recording permission) | Implemented-untested (X11; mss can't capture Wayland) |
| Tap-to-click on the preview (absolute click per monitor) | 6 | Tested: 5/5 calibration targets, worst error 1.7 px (limit 10 px), one 1920x1080 monitor at 125% | Implemented-untested | Implemented-untested (X11) |
| Multi-monitor picker | 6 | UI tested with a scripted two-monitor agent; offset maths unit-tested (negative and non-zero origins). Only one monitor exists on the dev laptop | same | same |
| Keys tab (send, live typing, quick keys, combos, shortcuts) | 7 | Tested in Playwright (scripted agent); key injection itself tested in Phase 2 | same (Cmd shortcuts) | same |
| Launcher: URL in preferred browser (Brave first) | 7 | Tested (real: opened a tab in Brave from its per-user install path) | Implemented-untested (`open -a`) | Implemented-untested (brave-browser / xdg-open) |
| Launcher: registered apps | 7 | Validation unit-tested (.exe/.lnk/.url/.appref-ms, absolute, existing); `os.startfile` not run in tests | Implemented-untested (bundle id or .app via `open`) | Implemented-untested (.desktop via `gio launch`, executables) |
| Scenes | 7 | Runner and socket flow tested with fakes | same | same |
| Sleep timer (minutes, end of media, 30s fade, restore volume) | 7 | Logic tested with fakes; end to end over the socket with a short timer | same | same |
| Brightness | 7 | Tested (real read 80% and write in 157 ms on the built-in BOE panel) | Unsupported (no public API for the built-in display) | Implemented-untested (screen-brightness-control) |
| AI planner (Ollama qwen2.5:7b, allowlist validation, one retry, confirm for risky steps) | 8 | Tested: 26 pytest cases with a scripted model, including the 5 spec examples executed against fakes; real model planned all 5 correctly in 2 of 2 runs (planning only, `docs/reports/ai-demo.log`), 8 to 22 s per request on CPU | Implemented-untested (provider code is OS independent) | Implemented-untested |
| AI providers Groq / Gemini | 8 | Request shapes unit-tested with a mock transport; no real call made (no keys) | same | same |
| AI screen (chat, suggestion chips, step chips, confirm sheet) | 8 | Tested in Playwright with a scripted agent (iPhone 15 WebKit, Pixel 8 Chromium). Real phone pending Sam | same | same |
| `--https` (uvicorn TLS with cert/key from config) | 8 | Tested: throwaway self-signed cert, `/api/health` over https, plain http refused, wss pairing reported `secureContext: true` | Implemented-untested | Implemented-untested |
| HTTPS with mkcert / Tailscale Serve | 8 | Documented in `docs/HTTPS.md`; neither tool is installed here, so not tested | same | same |
| Voice input (Web Speech) | 8 | Gating tested in Playwright (shown on secure pages when the browser has it, hidden on http). Speaking to a real phone pending Sam | same | same |
| Gyro air mouse | 8 | Mapping unit-tested; Playwright: motion events move the cursor only while holding, http shows the HTTPS help. Real phone feel pending Sam | same | same |
| Pause remote control | 9 | Tested (pytest over the socket; real dashboard click on a throwaway agent showed the paused banner) | same | same |
| Desktop dashboard `/desktop` (QR, devices, handling time, checklist, settings) | 9 | Tested: API and access rules in pytest; real page rendered in a browser on a throwaway agent with no console errors | Implemented-untested | Implemented-untested |
| Tray icon (pystray) | 9 | Tested: menu actions in pytest, tray mode with a server thread in pytest (fake icon), and a real tray-mode run that served `/api/health`. Clicking the real menu: pending Sam | Implemented-untested (pystray darwin backend) | Implemented-untested (needs an AppIndicator or X11 tray; falls back to no tray without a desktop session) |
| Start at login | 9, 11 | Tested: a Task Scheduler sign-in task (fake scheduler tests, plus a real create, read and delete of a scratch task). Turned on for real on this laptop and started through the task; it runs in the signed-in session. A real sign-in after a restart is pending Sam. (The Run key used before was skipped by Windows at a real sign-in, so it was replaced.) | Implemented-untested (LaunchAgent plist, contents unit-tested) | Implemented-untested (XDG autostart entry, contents unit-tested) |
| First-run guide | 9 | Tested: tray mode opens the dashboard when no phone is paired (pytest); guide shown while there are no devices | same | same |
| Packaged app (PyInstaller one-folder, windowed) | 9 | Tested: built, started from a throwaway home, served the remote and the dashboard, every feature reported ready, 500 pings p50 1.35 ms (localhost). Unsigned | Implemented-untested (`build_agent.py` has the options) | Implemented-untested |
| Idle cost: no polling while no phone is connected | 10 | Tested: 0.7% of one core with no phone (was 4.0%), 4.8% with a phone connected, 97 MB | Implemented-untested | Implemented-untested |
| Friendly errors: busy port, broken devices file (fails closed) | 10 | Tested (pytest) | same | same |
| Code-split phone app (largest chunk 211 kB, was 604 kB) | 10 | Tested: Lighthouse mobile performance 99, accessibility 100, best practices 100 | same | same |
| Real phone over Wi-Fi (feel, latency, PWA install) | all | Not tested by me: no phone is available to the build machine. Pending Sam's manual checks in each phase report | same | same |
| Send to laptop: clipboard both ways, links, file upload | 11 | Tested: pytest (fakes and a real clipboard round trip, restored afterwards), Playwright | Implemented-untested (pbcopy/pbpaste) | Implemented-untested (wl-copy/wl-paste or xclip) |
| Installed-app picker and Store apps by id | 11 | Tested: 171 real apps listed; a real Spotify WindowsApps path converted to its id | Implemented-untested (/Applications) | Implemented-untested (.desktop files) |
| Real shortcut icons | 11 | Tested: real app icons (Spotify, Brave, Notepad) and site icons (GitHub, Twitch, Reddit); LAN addresses refused. Wikipedia refuses automated requests, so it keeps the letter tile | Site icons only (no app icons) | Site icons only (no app icons) |
| Per-app layouts and call buttons | 11 | Tested: pytest and Playwright (Zoom Mute sends Alt+A). The Zoom, Teams and Meet shortcuts themselves are each app's own; a real call is pending Sam | same | same |
| Volume indicator on the laptop | 11 | Tested on this laptop at 0, 4 and 100%: the level never changed (restored afterwards) | n/a (no change on macOS) | n/a |
| Several laptops and Wake-on-LAN | 11 | Tested with two agents on this laptop: each found the other, a stopped one was marked asleep in 44 s, the wake packet was sent. Waking real hardware is pending Sam and depends on the laptop's BIOS and network card | Implemented-untested | Implemented-untested |
| Lock-screen controls | 11 | Tested in Playwright with a stubbed Media Session (both engines). A real phone lock screen is pending Sam | same | same |
| Light mode | 11 | Tested in Playwright (toggle, remembered, theme colour); contrast checked in unit tests | same | same |
| Power: lock / sleep / restart / shut down with confirm tokens | 7 | Token rules tested; real actions not run on purpose (pending Sam). Note: with hibernation enabled, Windows "sleep" hibernates | Implemented-untested (pmset / System Events) | Implemented-untested (loginctl / systemctl) |

Rows are added as each phase lands.

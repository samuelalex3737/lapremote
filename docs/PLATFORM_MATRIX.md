# Platform matrix

Legend: **Tested** = run and verified on that OS. **Implemented-untested** = code exists but has
not been run on that OS. **Unsupported** = will not work, with the reason.

Development host so far: Windows 11 Home Single Language, build 26300, one 1920x1080 display at
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

Rows are added as each phase lands.

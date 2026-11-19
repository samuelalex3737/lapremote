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

Rows are added as each phase lands.

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
| Remote web app (scaffold) | 0 | Tested in Playwright: iPhone 15 (WebKit), Pixel 8 (Chromium) | same | same |

Rows are added as each phase lands.

## PHASE 9 REPORT - Tray, desktop dashboard, start at login, packaging

### Files created/changed
- Agent:
  - new `tray.py`, `desktop.py`, `desktop_page.py`, `assets/dashboard.html`, `autostart.py`, `packaging/entry.py`
  - `__main__.py` (tray mode, `--no-tray`, no-desktop fallback, windowed-build streams)
  - `server.py` (dashboard and autostart wiring)
  - `core.py` (`revoke_device`, `set_device_role`, `set_paused`), `router.py` (pause gate, per-device handling times)
  - `pyproject.toml` / `uv.lock` (pystray; PyInstaller as a dev tool; mypy override for pystray)
- Agent tests: new `test_phase9.py` (13), `conftest.py` (environment isolation), `fakes.py` (`FakeAutostart`), `wsclient.py` (fake autostart), `test_main.py` (never takes the tray path)
- Scripts: new `scripts/build_agent.py`
- Docs: README (run, tray, build), SECURITY, PLATFORM_MATRIX, TESTING, ARCHITECTURE, CHANGELOG

### Commands run (real output, trimmed)
```
$ uv run python -m pytest tests/test_phase9.py
13 passed
$ python -m lapremote --port 7798 --input-dry-run        (tray mode, throwaway seeded home)
health: {"ok":true,"version":"0.1.0","uptime":2.8}
desktop from 127.0.0.1: 200
desktop with LAN Host header: 404
  (dashboard opened in a browser: QR, code, devices, checklist, settings; no console errors;
   ticking Pause showed the paused banner)
$ uv run --project agent python scripts/build_agent.py --skip-web
[build_agent] built C:\dev\lapremotegent\dist\LapRemote\LapRemote.exe (59 MB folder)
$ LapRemote.exe --port 7799 --input-dry-run               (throwaway seeded home)
health: {"ok":true,"version":"0.1.0","uptime":3.0}
remote app: 200   dashboard: 200
checklist: input, media (GSMTC), volume, brightness, preview, context, power, launcher, ai all ready
shortcuts.json and scenes.json seeded from the bundled lapremote/defaults
$ scripts/measure.py ping --port 7799                     (packaged app, localhost)
ping x500: p50 1.35 ms, p95 2.25 ms, max 5.09 ms
$ scripts/measure.py idle --port 7799
idle 30s: agent CPU 5.50% of one core (0.46% of all cores), memory 102.2 MB
$ uv run --project agent python scripts/check.py
  (all steps PASS; see the commit)
```

### Done criteria
- [x] pystray tray menu: QR (Pair a phone), devices, pause remote control (rejects input; `config.remoteControlPaused`), open dashboard, start at login, logs folder, quit - evidence: `test_tray_menu_and_actions`, `test_tray_mode_serves_in_a_thread_and_quits` (a menu click from the tray thread reached the agent's loop), and a real tray-mode run that served `/api/health`.
- [x] Localhost-only `/desktop` dashboard: QR with regenerate, devices, latency, permission checklist, settings - evidence: `test_dashboard_*` (404 for other machines and for a rebinding Host, 403 without the header or with a foreign Origin, CSP nonce, no framing), and the real page in a browser (no console errors; clicking Pause showed the banner). For "latency", see deviations.
- [x] Pause remote control rejects input - evidence: `test_pause_refuses_control_but_keeps_phones_connected` (click refused, moves dropped, ping still answered, toasts both ways, flag saved).
- [x] Autostart: Windows Run key, macOS LaunchAgent, Linux XDG - evidence: `test_windows_autostart_quotes_paths_with_spaces`, `test_mac_and_linux_autostart_files`, `test_real_registry_round_trip_on_a_scratch_key`.
- [x] PyInstaller one-folder build via `scripts/build_agent.py`, with the web build and shared defaults in `lapremote/defaults` - evidence: see the commands above.
- [x] First-run guide - evidence: the dashboard shows the guide while no phone is paired, and tray mode opens it on first run (`test_tray_mode_serves_in_a_thread_and_quits` checks the URL that opened).
- [ ] Real tray clicks, start at login after a real reboot, and the packaged app on a clean machine - pending Sam (below).

### Manual checks for Sam (on the laptop)
1. **Tray.** Run `cd agent && uv run python -m lapremote`. A LapRemote icon appears in the tray (it may be in the overflow arrow). Right-click it: every item is there. "Open dashboard" opens the dashboard.
2. **Pause.** With the phone connected, tick "Pause remote control" in the tray. The phone shows "Remote control is paused on the laptop." and the trackpad does nothing. Untick it and control comes back.
3. **Dashboard.** At http://127.0.0.1:7777/desktop: the QR pairs a phone, "New code" changes it, devices show Online, and Make guest / Remove work. From the phone's browser, `http://<laptop-ip>:7777/desktop` should be "Not Found".
4. **Start at login.** Tick "Start at login" in the tray, sign out and back in. LapRemote should start with no console window. Untick it afterwards if you don't want it.
5. **Packaged app.** Run `agent\dist\LapRemote\LapRemote.exe`. If Windows Smart App Control or SmartScreen blocks it, see the known issues. Otherwise the tray icon appears and the phone connects.
6. **Quit.** Tray > Quit LapRemote: the icon goes away and the phone shows offline.

### Known issues / deviations / protocol change proposals
- **Latency in the dashboard.** The agent can't measure the network round trip by itself: only the phone sees `pong`. So the dashboard shows the laptop's own handling time per device (median and 95th percentile of the last 200 commands) and says that the phone's status bar shows the full round trip. If you want the round trip on the laptop too, a small protocol addition would do it (for example, the phone includes its last measured round trip in `ping`). Waiting for your approval.
- The `features.state` push proposed in Phase 8 is still pending. Until then, the dashboard's checklist is live, but the phone only sees changes when it reconnects.
- Settings changed in the dashboard are saved and take effect after a restart (it says so). Pause and start at login take effect at once.
- Pause doesn't stop a sleep timer or an AI plan that is already running.
- The real tray menu was not clicked by me (no desktop automation), and the real Windows Run key was not written. Only a scratch key was round-tripped and then deleted.
- During development, one test run took the tray path before I guarded it. That may have briefly shown a tray icon and opened a browser tab to a throwaway dashboard on your laptop. Tests now never take that path unless they inject a fake icon.
- The packaged app is unsigned. On this laptop it ran without being blocked, but on other machines
  SmartScreen may ask "Windows protected your PC" (More info > Run anyway), and Smart App Control
  can block unsigned apps outright. Code signing costs money, so it's out of scope. Running from
  source always works.
- The build is Windows only so far. `build_agent.py` has the macOS and Linux options, but they
  haven't been run.
- Idle CPU of the packaged app is 5.5% of one core (0.46% of all cores). It comes from the 500 ms
  volume and context polls plus the media watcher. I'll look at it in Phase 10.
- `scripts/measure.py ping` used to send pings back to back, faster than the 300 messages/s
  limit, so a rate-limited ping never got its pong. It now waits 5 ms between pings, like a real
  phone.

### Self-check (Section 12)
1. **Placeholders?** None (grep clean).
2. **Linters and tests?** All `check.py` steps pass.
3. **Evidence?** Yes: tests, a real tray-mode run, the real dashboard in a browser, and the packaged build. Real clicks and a reboot are pending.
4. **protocol.py vs protocol.ts?** They match. No protocol change (the pause refusal uses the existing `ack` error and `toast`).
5. **Anything running user-controlled strings?** No. Autostart writes a fixed command built by the agent. Opening the logs folder passes only LapRemote's own folder to a fixed program. The dashboard is local-only, CSRF-guarded and CSP-locked.
6. **Safe areas, 44px targets, reduced motion, contrast?** The phone UI is unchanged. The dashboard is a desktop page with 40px controls, visible focus rings, and light and dark themes.
7. **Copy and dashes?** Short ("Remote control is paused on the laptop."). No long dashes.
8. **Docs updated?** README, SECURITY, PLATFORM_MATRIX, TESTING, ARCHITECTURE and CHANGELOG.
9. **Honest known issues?** Yes, listed above.
10. **Committed?** Yes, as `feat(phase-9)`.

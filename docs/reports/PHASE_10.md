## PHASE 10 REPORT - Hardening, measurements, docs, v1.0.0

### Files created/changed
- Agent:
  - `system/{volume,context,brightness}.py` (no polling without phones, fresh read on connect)
  - `security/pairing.py` (broken devices file fails closed), `__main__.py` (busy-port message)
  - version 1.0.0 in `__init__.py`, `pyproject.toml` and `uv.lock`
- Agent tests: new `test_phase10.py` (6), `fakes.py` (`FakeVolume.reads`), `test_main.py` (port check stubbed)
- Web: `app/Shell.tsx` (lazy tabs plus idle prefetch), `vite.config.ts` (vendor chunks), version 1.0.0
- Scripts: `measure.py` (`moves`, `idle --home`)
- Docs: README (rewritten), new `DEMO_SCRIPT.md`, SECURITY (threat model, process audit, residual risks), PLATFORM_MATRIX, TESTING (measurements), CHANGELOG (1.0.0)

### Commands run (real output, trimmed)
```
$ measure.py idle --port 7801                          (before: polling always on)
idle 30s: agent CPU 4.00% of one core (0.33% of all cores), memory 96.9 MB
$ measure.py idle --port 7801                          (after)
idle 30s: agent CPU 0.70% of one core (0.06% of all cores), memory 96.7 MB
$ measure.py idle --port 7801 --home ...               (a phone connected)
idle 30s (phone connected): agent CPU 4.80% of one core (0.40% of all cores), memory 96.9 MB
$ measure.py ping --port 7801 --home ...
ping x500: p50 0.64 ms, p95 1.02 ms, max 172.38 ms
$ measure.py moves --port 7801 --home ...              (120/s and 240/s for 10 s)
input.move: sent 1200 in 10.0s (120/s)  agent CPU 7.3%   ping right after 0.74 ms
input.move: sent 2400 in 10.0s (240/s)  agent CPU 13.6%  ping right after 0.78 ms
$ measure.py preview --port 7801 --home ...
7.87 fps, 87.4 KB/s (0.72 Mbit/s), median frame 11.1 KB, agent 21.6% of one core, 113.0 MB
$ npm run build                                        (code-split)
react 210.53 kB, motion 151.60 kB, zod 91.88 kB, index 56.26 kB, MoreTab 28.16 kB, TrackpadTab 25.89 kB ...
(no "chunks larger than 500 kB" warning; the main chunk was 603.94 kB)
$ npm run lighthouse -- http://127.0.0.1:7801/
performance 99, accessibility 100, best-practices 100, seo 63 (only is-crawlable fails: robots.txt)
FCP 1.1 s, LCP 1.1 s, TBT 110 ms, CLS 0.001
$ grep for subprocess / create_subprocess_exec / os.startfile / os.system / shell=True / eval / exec / webbrowser.open
every hit is in the SECURITY.md table; no shell=True, eval or exec
$ uv run --project agent python scripts/check.py
  PASS ruff check, ruff format, mypy --strict, protocol schema, pytest (313, then 314 with the
  media fallback test), eslint, tsc, vitest (216), playwright (77)
$ uv run --project agent python scripts/build_agent.py
[build_agent] built C:\dev\lapremotegent\dist\LapRemote\LapRemote.exe (60 MB folder)
```

### Done criteria
- [x] Latency p50/p95 over 500 pings - evidence: above (localhost; the Wi-Fi round trip needs a real phone, which shows it in its status bar).
- [x] `input.move` rate - evidence: 120/s and 240/s handled with no backlog.
- [x] Idle CPU and memory - evidence: 0.7% of one core with no phone (down from 4.0%), 4.8% with a phone connected, 97 MB.
- [x] Preview bandwidth - evidence: 87 KB/s at 8 fps / 480 px.
- [x] SECURITY.md threat model plus the subprocess grep - evidence: `docs/SECURITY.md` (threat table with residual risk per row, audited process table).
- [x] Resilience checks - evidence: `test_phase10.py` (resume after an agent restart, broken devices file fails closed, busy port, vanishing volume device, a media backend failing at start falls back to media keys), plus the existing tests for broken config, bad input, rate limits and Ollama not running.
- [x] Honest PLATFORM_MATRIX - evidence: new rows, including an explicit "real phone over Wi-Fi: not tested by me" row.
- [x] Full README (install, dev, build, pairing, HTTPS, Tailscale, AI setup, troubleshooting, roadmap), DEMO_SCRIPT.md, CHANGELOG.
- [x] Code-splitting the main chunk - evidence: build output and Lighthouse above.
- [x] Tag v1.0.0 - evidence: `git tag` (local only, not pushed).

### Manual checks for Sam
1. Work through `docs/DEMO_SCRIPT.md` on your real phone. It covers every feature in about 5 minutes.
2. The real-phone checks from each phase report (PHASE_1 to PHASE_9) are still open. The most important ones: trackpad feel, Now Playing with real apps, a real lock from the Power screen, the tray menu, and start at login after signing out and back in.
3. Look at the phone's status bar for the Wi-Fi round trip and tell me what it shows. I could only measure localhost.

### Known issues / deviations / protocol change proposals
- **Open protocol proposals, waiting for your approval:** (1) a `features.state` push, so the AI screen notices Ollama starting without reconnecting; (2) the phone reporting its round trip, so the dashboard can show network latency. Neither is implemented.
- Real-phone checks were never possible from the build machine. Everything phone-side was tested in Playwright with iPhone 15 (WebKit) and Pixel 8 (Chromium) emulation.
- macOS and Linux are implemented but untested.
- With a phone connected, idle CPU is 4.8% of one core because volume and the foreground app are checked every 500 ms (needed for live updates). It is 0.4% of all cores.
- One 172 ms ping outlier in 500 on localhost (p95 1.02 ms), likely OS scheduling. Not reproduced.
- SEO 63 in Lighthouse is on purpose: `robots.txt` keeps search engines away from a private remote.
- v1.0.0 is tagged locally only. Nothing was pushed.

### Self-check (Section 12)
1. **Placeholders?** None (grep clean).
2. **Linters and tests?** All `check.py` steps pass.
3. **Evidence?** Yes: measurements, tests and Lighthouse. Real-phone checks are pending.
4. **protocol.py vs protocol.ts?** They match. No protocol change in this phase.
5. **Anything running user-controlled strings?** No. The process audit is in SECURITY.md.
6. **Safe areas, 44px targets, reduced motion, contrast?** Unchanged and still covered by e2e. Lighthouse accessibility is 100.
7. **Copy and dashes?** Short copy. No long dashes.
8. **Docs updated?** README, DEMO_SCRIPT, SECURITY, PLATFORM_MATRIX, TESTING and CHANGELOG.
9. **Honest known issues?** Yes, listed above.
10. **Committed?** Yes, as `feat(phase-10)`, and tagged `v1.0.0`.

## PHASE 6 REPORT - Live screen preview and tap-to-click

### Files created/changed
- Agent:
  - `preview/{__init__,capture,calibration}.py`
  - `input/mouse.py`: `move_to`, `click_at`
  - `input/service.py`: `input.absclick`, `ScreenRect`, `absolute_point`
  - `server.py`: preview wiring, `/calibration`, `grabber` knob
- Agent tests: `test_preview.py` (14), `test_input.py` (recorder `move_to`), `wsclient.py` (no real capture in tests)
- Web:
  - `lib/preview.ts`, `lib/ws.ts` (binary frames), `store/remote.ts` (`binaryType = 'arraybuffer'`)
  - `features/preview/ScreenPreview.tsx`, `features/trackpad/TrackpadTab.tsx` ("Trackpad | Screen")
- Web tests:
  - `unit/preview.test.ts`
  - `e2e/preview.spec.ts`, `e2e/fakeAgent.ts` (binary frames, monitors), `e2e/frame-480x270.jpg`
  - `accuracy/tapAccuracy.ts`
- Scripts: `scripts/measure.py`
- Docs: PLATFORM_MATRIX, CHANGELOG, TESTING, SECURITY, README

### Commands run (real output, trimmed)
```
$ uv run --project agent python scripts/measure.py preview --home <throwaway> --port 7795 --seconds 20
preview 8fps / 480px for 20.0s
  frames received     155 (7.75 fps)
  bandwidth           108.1 KB/s (0.89 Mbit/s)
  frame size          median 14.3 KB, max 15.5 KB
  agent CPU           16.8% of one core (1.4% of all 12 cores)
  agent memory (RSS)  96.3 MB
```
The first version converted BGRA to RGB in Python (mss `.rgb`) and resized the full frame. It
measured 38.4% of one core at 79 KB/s. Native BGRX decoding plus an integer `reduce()` halved the
CPU. Frames are a little larger (14 KB vs 10 KB) because the box filter keeps more detail.

```
$ node tests/accuracy/tapAccuracy.ts 7795 <deviceId> <token>     (agent with real input)
frame 1920x1080, targets found: 5
clicks acked: ok, ok, ok, ok, ok
tap 1: target 1 at (129, 93) 0.8 px off
tap 2: target 2 at (1164, 93) 1.6 px off
tap 3: target 3 at (647, 468) 1.3 px off
tap 4: target 4 at (129, 844) 1 px off
tap 5: target 5 at (1164, 844) 1.7 px off
targets hit: 5/5, worst error 1.7 px (limit 10 px)
```
How it works: the targets are found by colour in a real preview frame, sent as `input.absclick`
with normalised coordinates, and turned into real clicks by the agent. The calibration page
measures each click in physical pixels.

```
$ uv run --project agent python scripts/check.py
  PASS ruff / format / mypy --strict / protocol schema
  PASS pytest (245)
  PASS eslint / tsc
  PASS vitest (179)
  PASS playwright (55 passed)
```

### Automated tests
- pytest 245 passed (14 preview).
- vitest 179 passed (8 preview).
- Playwright 55 passed: 4 preview specs on two devices; the hold test is Chromium only.

### Done criteria
- [x] Capture at the requested fps (default 8, max 15) and width (default 480), JPEG quality 60, binary frames - evidence: the measurement above, `test_preview_streams_with_backpressure`. fps is capped by `PreviewStart` validation (1-15).
- [x] Backpressure: never more than 2 unacked frames, capture skipped while behind, `preview.ack` per frame - evidence: the test shows no capture without acks, and frames 3 and 4 follow an ack of frame 2.
- [x] Stops on `visibilitychange`, socket close and unmount - evidence: e2e "stop on leave", the disconnect hook in `PreviewService`, the visibility listener in `ScreenPreview`.
- [x] Multi-monitor picker from `preview.meta.monitors` - evidence: e2e with two monitors (`monitor: 1` requested).
- [x] Tap-to-click maps normalised coordinates to absolute physical pixels including offsets and DPI. Long-press gives a right click, and a ripple shows - evidence: `test_absolute_point` (5 layouts), `test_absclick_maps_to_the_right_monitor`, e2e centre tap (0.5, 0.5), the e2e hold test.
- [x] Local pinch-zoom of the preview - evidence: `zoomAt`, `clampView` and `tapToNormalised`-under-zoom unit tests.
- [x] The preview is a toggle at the top of the Trackpad tab - evidence: e2e `openScreen`.
- [x] Bandwidth and CPU at 8 fps/480 px reported - evidence: above.
- [x] Tap accuracy: 5 targets on `/calibration` land within 10 px on every monitor - evidence: above, worst 1.7 px. This laptop has one monitor. Multi-monitor offsets are covered by unit tests only.

### Manual checks for Sam (on real phone + laptop)
1. Rebuild the web app and restart the agent. Open Trackpad, then Screen -> the laptop screen appears within a second and updates live.
2. Tap a desktop icon in the preview -> the cursor jumps there and clicks. A white ripple shows where you tapped.
3. Press and hold on an icon -> a right-click menu opens on the laptop, with an amber ripple.
4. Pinch the preview to zoom in, then tap a small button -> it clicks precisely. Tap "Fit" to zoom back out.
5. Lock the phone or switch apps for a moment -> the laptop stops capturing (the agent log shows `preview_stopped`). Come back -> it resumes.
6. Optional: open `http://<laptop>:7777/calibration` on the laptop in full screen and tap the pink targets from the phone. The page shows each error in pixels.

### Known issues / deviations / protocol change proposals
- No protocol changes.
- Playwright's bundled Chromium can't start in headed mode in this environment (`spawn UNKNOWN`), so the accuracy script uses the installed Chrome with a throwaway profile. Headless test runs are unaffected.
- On macOS, capture needs the Screen Recording permission. It isn't checked for yet; the Phase 9 permission checklist will cover it. On Linux, capture works on X11 only.
- Long-press right-click fires after 500 ms of holding without moving. Holding still on the preview to read it will right-click, so a moved finger cancels it. The threshold is 10 px.
- The preview width is fixed at 480 px (the spec default) with pinch-zoom for precision. A sharper-preview setting is not exposed yet.

### Self-check (Section 12)
1. **Placeholders?** None (grep clean).
2. **Linters and tests?** All `check.py` steps pass.
3. **Evidence?** Yes, real measurements and a real-click accuracy run.
4. **protocol.py vs protocol.ts?** They match (unchanged, sync tests pass).
5. **Anything running user-controlled strings?** No. Absolute clicks are bounded floats mapped to a known monitor.
6. **Safe areas, 44px targets, reduced motion, contrast?** Yes. The preview e2e runs the 44 px target check, and ripples respect reduced motion through MotionConfig.
7. **Copy and dashes?** Short ("Tap to click · hold for right click"). No long dashes.
8. **Docs updated?** PLATFORM_MATRIX, CHANGELOG, TESTING, SECURITY and README are updated.
9. **Honest known issues?** Yes, listed above.
10. **Committed?** Yes, as `feat(phase-6)`.

## PHASE 2 REPORT - Input engine and trackpad gestures

### Files created/changed
- Agent: `input/{__init__,mouse,keyboard,service}.py`, `system/dpi.py`, `system/permissions.py`;
  `core.py` (disconnect hooks), `server.py` (DPI awareness, input wiring), `__main__.py`
  (`--input-dry-run`)
- Agent tests: `test_input.py`. `wsclient.py` now always uses dry-run input, so tests never move
  the real cursor.
- Web: `lib/gestures/{trackpad,acceleration,sender,controller,combos,settings}.ts`, `lib/haptics.ts`,
  `lib/hints.ts`, `features/trackpad/{Trackpad,GestureHints,TrackpadSettingsPanel}.tsx`,
  `app/Toaster.tsx`, `app/App.tsx`, `styles.css`
- Web tests: `unit/gestures.test.ts`, `e2e/trackpad.spec.ts`. `playwright.config.ts` now runs the
  agent with `--input-dry-run`.
- Docs: PROTOCOL (clarification 8), PLATFORM_MATRIX, CHANGELOG, TESTING, README

### Commands run (real output, trimmed)
```
$ uv run --project agent python scripts/check.py
  PASS ruff check / ruff format / mypy --strict / protocol schema
  PASS pytest (157 passed)
  PASS eslint / tsc --noEmit
  PASS vitest (145 passed)
  PASS playwright (13 passed, 1 skipped: the multi-touch test runs on Chromium only)
```
Real cursor check on this laptop (after DPI awareness):
```
dpi: per_monitor
screen (physical): 1920 x 1080
start (934, 614) after +41 (975, 614) back (934, 614)
```
The cursor was moved with 4 x 10.25 px through `Mouse.move`, which shows the sub-pixel carry
sends exactly 41 px.

### Automated tests
- pytest 157 passed (23 new input tests).
- vitest 145 passed (44 gesture tests).
- Playwright 13 passed and 1 skipped (WebKit can't drive multi-touch over CDP).

### Done criteria
- [x] `mouse.py`: relative move, click, down/up, high-resolution scroll, zoom - evidence: `test_input.py`, the real cursor check.
- [x] Windows `SetProcessDpiAwareness(2)` at startup - evidence: `dpi: per_monitor`, `test_dpi_awareness_is_set_once`.
- [x] macOS: missing Accessibility is detected and a toast gives exact steps - evidence: `test_unavailable_input_warns_the_owner`, `test_input_permission_matrix`. Not run on a Mac.
- [x] Linux: Wayland reported, not faked - evidence: `test_unavailable_input_is_reported`.
- [x] Gesture state machines, pure and unit-tested, for every rule:
  - [x] 1-finger drag with acceleration, sub-pixel carry and one message per frame
  - [x] Tap: under 180 ms and under 6 px
  - [x] Tap-then-hold-drag: second press within 250 ms
  - [x] Long-press drag lock: 450 ms, released by the next tap
  - [x] 2-finger tap: under 200 ms and under 8 px
  - [x] 2-finger scroll with inertia: x0.95 per frame until under 0.5
  - [x] Natural scroll
  - [x] Pinch: 8%, re-baselined, 120 ms debounce
  - [x] 3-finger swipe: over 40 px
  - [x] Right-edge strip: 12%

  Evidence: `gestures.test.ts`.
- [x] Edge cases - evidence:
  - a tap that moves 7 px is not a tap
  - pinch plus drift does not scroll
  - plus: holding 180 ms is not a tap, a leftover finger after scrolling doesn't move the cursor, cancel during a drag releases the button, the 40 px swipe boundary
- [x] Surface uses `touch-action: none`, blocks Safari pinch, has no text selection or callout - evidence: e2e checks the computed `touch-action`.
- [x] Settings for sensitivity, acceleration, natural scroll, tap-to-click and 3-finger mappings, saved in localStorage - evidence: e2e "settings open, change and persist", unit settings tests.
- [x] Haptics: click 8 ms, right click 15 ms, drag lock [10, 40, 10], no-op on iOS - evidence: `haptics` unit test.
- [x] Faint instruction overlay until the first touch - evidence: e2e hints visible, then hidden after a tap.
- [ ] Manual: Sam moves, clicks, right-clicks, scrolls with inertia, pinch-zooms and drag-selects on a real phone - **pending Sam**. End to end in emulation: tap -> `input.click`, drag -> moves, two-finger drag -> scrolls (agent dry-run log).

### Manual checks for Sam (on real phone + laptop)
1. `uv run --project agent python scripts/build_web.py`, then `cd agent && uv run python -m lapremote`, then pair the phone -> the trackpad screen shows the gesture hints.
2. Slide one finger -> the cursor follows smoothly, and faster flicks travel further.
3. Tap -> left click. Double tap on a word -> it gets selected.
4. Two-finger tap -> context menu.
5. Two-finger drag on a long web page, then lift -> the page keeps gliding and slows down.
6. Pinch out in the browser -> the page zooms in (Ctrl +). Pinch in -> it zooms out.
7. Tap, then quickly touch again and slide over some text -> the text is selected. Lift -> the selection ends.
8. Press and hold 0.5 s (phone buzzes on Android) -> slide, lift, slide again -> it is still dragging. Tap once -> it releases.
9. Three-finger swipe up -> Task view. Down -> desktop. Left/right in a browser -> previous/next tab.
10. Slide up and down along the right edge -> it scrolls without moving the cursor.

### Known issues / deviations / protocol change proposals
- Tap-then-drag: the first tap's click is sent right away (spec: no delayed clicks), so the OS sees click + press. In text editors this starts a word-wise selection. That is the same as on a physical trackpad with tap-to-click.
- `input.scroll` units (wheel notches, `dy > 0` = view down) are now written down as clarification 8. This is not a contract change.
- The three-finger shortcuts on Linux depend on the desktop (Super+S is the GNOME overview, Super+D isn't bound in GNOME by default). macOS uses Ctrl+Up and F11 (the defaults). Neither has been tested on those systems.
- Windows blocks injected input into apps running as administrator (UIPI). LapRemote can't click inside elevated windows unless the agent also runs elevated. Documented here and in the platform matrix notes.
- Settings and devices still sit on one simple screen. The tab bar and design system arrive in Phase 4.
- In the e2e tests, multi-touch only runs in Chromium (WebKit has no CDP touch driver). Gestures are covered by unit tests on both.
- Real-phone feel (speed, acceleration defaults) still needs Sam's check. The settings let you tune it.

### Self-check (Section 12)
1. **Placeholders?** None (grep clean).
2. **Linters and tests?** All 9 `check.py` steps pass.
3. **Evidence?** Yes, except the real-phone manual check, which is marked pending.
4. **protocol.py vs protocol.ts?** They match (the sync tests pass, and the protocol is unchanged).
5. **Anything running user-controlled strings?** No. Key names are allowlisted, and text is typed, never run.
6. **Safe areas, 44px targets, reduced motion, contrast?** Safe areas are handled. Buttons are 56px high and settings controls at least 44px. No animation yet. AA contrast.
7. **Copy and dashes?** Short and friendly. No long dashes.
8. **Docs updated?** PROTOCOL, PLATFORM_MATRIX, CHANGELOG, TESTING and README are updated.
9. **Honest known issues?** Yes, listed above.
10. **Committed?** Yes, as `feat(phase-2)`.

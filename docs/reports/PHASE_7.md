## PHASE 7 REPORT - Keyboard, launcher, scenes, timer, power

### Files created/changed
- Agent:
  - `shortcuts.py`, `scenes.py`, `timer.py`, `actions.py`, `services.py`, `storage.py`
  - `system/{brightness,power}.py`
  - `server.py` (uses `build_services`, keeps `app.state.services`)
  - `__main__.py`, and `pyproject.toml` (screen-brightness-control, mypy override)
- Shared: `shared/{shortcuts,scenes}.default.json`
- Agent tests: `test_phase7.py` (20), and `fakes.py` (FakePower, FakeLauncher, FakeBrightness).
  `wsclient.py` always injects the fake power and launcher, so tests never act on the laptop.
- Web:
  - `lib/{keys,timer,shortcuts,scenes}.ts`, `lib/protocol.ts` (`PowerActionName`)
  - `store/remote.ts` (`useExtras`), `store/ui.ts` (`timerThen`), `app/useClock.ts`
  - `features/keyboard/KeysTab.tsx`, `features/launcher/{LaunchTab,launch,shortcutIcon}`
  - `features/{scenes,timer,power}/*Screen.tsx`, `features/nowplaying/extras.tsx`, `features/more/MoreTab.tsx`
- Web tests: `unit/phase7.test.ts` (12), `e2e/phase7.spec.ts` (6 specs x 2 devices), `e2e/fakeAgent.ts`
- Docs: PLATFORM_MATRIX, CHANGELOG, TESTING, SECURITY

### Commands run (real output, trimmed)
```
$ uv run --project agent python scripts/check.py
  (all steps PASS; see the commit)
$ uv run python -m pytest tests/test_phase7.py
20 passed
$ npx playwright test tests/e2e/phase7.spec.ts
12 passed (30.1s)
```
Real laptop (no power action was run on purpose):
```
brave exe: C:\Users\<you>\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe
open_url: started                                   (an example.org tab opened in Brave)
brightness set to its current value 80 -> 80 (157 ms)
```

### Done criteria
- [x] Keys tab:
  - text field that sends `key.text` on submit, or live
  - quick keys: Esc, Tab, Enter, Backspace, Space, arrows, F, and Win/Cmd as Start/Spotlight/Activities
  - combo builder, and common shortcuts (copy, paste, undo, close tab, new tab, Alt+Tab)

  Evidence: the e2e keys test asserts every sent payload; `liveDiff` unit tests.
- [x] Launch tab from `~/.lapremote/shortcuts.json`, seeded with Netflix, YouTube, YouTube Music, Prime Video and Spotify, plus an "Open URL" sheet - evidence: e2e launch test, `test_defaults_are_seeded_once`.
- [x] `url` opens in the configured browser (Brave preferred). `app` launches only by a registered path or bundle id - evidence: the real Brave launch, `test_app_target_validation`.
- [x] The owner can add, edit, reorder and delete from the phone. Paths are validated and stored. No command strings - evidence: `test_launcher_over_socket` (a bad path is refused), the e2e launch test, the SECURITY table.
- [x] Scenes:
  - JSON step lists with the defaults Movie Night and Focus Music, and an editor on the phone

  Evidence: `test_scene_steps_run_in_order_and_survive_failures`, `test_scene_over_socket` (volume 40, brightness 60 and the Netflix URL really applied), the e2e scenes test.
- [x] Sleep timer:
  - presets plus end of track (disabled when unknown)
  - pause / pause + lock / pause + sleep
  - live countdown on Now Playing and in `timer.state`
  - 30-second fade with the volume restored afterwards

  Evidence: `test_timer_fades_pauses_restores_and_locks`, `test_timer_cancel_mid_fade_restores_volume`, `test_seconds_until_end`, `test_timer_over_socket`, the e2e timer test.
- [x] Power: hold-to-confirm (1.2 s) and a server `confirmToken` valid for 10 s - evidence: `test_power_tokens_expire_are_single_use_and_bound_to_the_action`, `test_power_over_socket`, the e2e test (releasing after 0.4 s sends nothing; holding 1.5 s sends prepare and then the action with the token).
- [x] pytest for the scene runner, timer maths including end-of-media, and power token expiry - evidence: `test_phase7.py`.
- [ ] Manual checklist on a real phone - pending Sam (below).

### Manual checks for Sam (on real phone + laptop)
1. **Keys.** Type in Send mode, then tap Send -> the text appears where the laptop cursor is. In Live mode each letter appears as you type, and deleting on the phone deletes on the laptop.
2. **Keys combos.** Tap Copy and Paste around some text -> it copies and pastes. Use Ctrl+Shift then T in the combo builder in a browser -> the last closed tab reopens.
3. **Launch.** Tap Netflix -> Netflix opens in Brave. Use "Open a website", type youtube.com, then Open once -> it opens and isn't added to the grid.
4. **Launch apps.** Add an app shortcut with the full path to an .exe (for example VLC) -> it launches. Edit mode lets you reorder and delete.
5. **Scenes.** Run Movie Night -> the volume goes to 40, the brightness to 60, Netflix opens, and the toast says "Movie Night is on."
6. **Timer.** Pick + Lock, then 15 min. Let it run (or use a short end-of-track) -> the volume fades over the last 30 s, playback pauses, the volume comes back, and the laptop locks.
7. **Power.** Hold Lock for about 1.2 s -> the laptop locks. Let go early -> nothing happens.
8. **Brightness.** Move the slider on the Power & display screen -> the screen brightness follows.

### Known issues / deviations / protocol change proposals
- No protocol changes. "Open once" uses an internal shortcut id `_once` (allowed by the existing id pattern). It is hidden from the grid and overwritten on each use.
- `protocol.ts` builds `KEY_NAMES` from spread arrays, so the web-side `KeyName` type is effectively `string`. Values are still checked at runtime by the zod enum and by the agent's allowlist, so this is a typing weakness only.
- Windows "sleep" calls `SetSuspendState`. With hibernation enabled, the laptop hibernates instead. Documented in the platform matrix.
- Real lock, sleep, restart and shut down were not run, to avoid disrupting your session. They are pending your manual check.
- `wmi` (a dependency of screen-brightness-control) prints two SyntaxWarnings about escape sequences on import. That is upstream and harmless.
- Reordering shortcuts uses earlier/later buttons in Edit mode, not drag-and-drop.

### Self-check (Section 12)
1. **Placeholders?** None (grep clean). The More screens are now real, and only AI is still gated (Phase 8).
2. **Linters and tests?** All `check.py` steps pass.
3. **Evidence?** Yes. Power actions and real-phone feel are pending.
4. **protocol.py vs protocol.ts?** They match (sync tests pass, no change).
5. **Anything running user-controlled strings?** No. URLs must be http(s) and are passed as a single argument. App targets are validated and stored, then run with no arguments and no shell. Power uses fixed arguments.
6. **Safe areas, 44px targets, reduced motion, contrast?** Yes. Every new screen passes the 44px target and no-horizontal-scroll checks in e2e.
7. **Copy and dashes?** Short ("Movie Night is on.", "Hold to confirm"). No long dashes.
8. **Docs updated?** PLATFORM_MATRIX, CHANGELOG, TESTING and SECURITY are updated. PROTOCOL is unchanged.
9. **Honest known issues?** Yes, listed above.
10. **Committed?** Yes, as `feat(phase-7)`.

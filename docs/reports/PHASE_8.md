## PHASE 8 REPORT - AI commands and secure-context features

### Files created/changed
- Agent:
  - new `ai/{__init__,providers,planner,service}.py`
  - `protocol.py` (`AiWait`, `AI_PAYLOADS`), `router.py` (background handlers), `services.py` (AI wiring, `input` and `context` on `Services`)
  - `input/service.py` (`press_key`, `type_text`), `media/service.py` (`select`), `system/volume.py` (`step`, `set_muted`)
  - `server.py` and `__main__.py` (`--https`)
  - `pyproject.toml` / `uv.lock` (httpx moved to a runtime dependency)
- Agent tests: new `test_ai.py` (26), `test_main.py` (+4 HTTPS), `fakes.py` (`ScriptedProvider`), `wsclient.py` (AI off unless a scripted provider is passed)
- Web:
  - `lib/{ai,airmouse,secure}.ts`, `store/ai.ts`
  - `features/ai/AiScreen.tsx`, `features/secure/NeedsHttps.tsx`, `features/trackpad/AirMouse.tsx`
  - `features/trackpad/{TrackpadTab,TrackpadSettingsPanel}.tsx`, `lib/gestures/settings.ts` (air mouse settings), `features/more/MoreTab.tsx`
- Web tests: `unit/ai.test.ts` (25), `e2e/phase8.spec.ts` (5 specs x 2 devices), `e2e/fakeAgent.ts` (scripted AI plans)
- Scripts: `scripts/ai_smoke.py` (check, demo, ask; plans only, never runs actions)
- Docs: new `AI.md`, `HTTPS.md`, `reports/ai-demo.log`; updated PROTOCOL (clarification 11), SECURITY, PLATFORM_MATRIX, TESTING, ARCHITECTURE, README, CHANGELOG

### Commands run (real output, trimmed)
```
$ ollama list                      (installed with winget 0.40.16; it was not installed before)
qwen2.5:7b    845dbda0ea48    4.7 GB
$ uv run --project agent python scripts/ai_smoke.py check
memory: 15.7 GiB usable (about 16 GB installed)
recommended Ollama model: qwen2.5:7b
configured: provider=ollama model=qwen2.5:7b
ready
$ uv run --project agent python scripts/ai_smoke.py demo --out docs/reports/ai-demo.log
> pause everything   (9391 ms)
  actions: media.pause spotify-1, media.pause chrome-1
> next episode and volume 30   (10848 ms)
  actions: media.next chrome-1, volume.set 30
> open youtube and search lofi beats   (19652 ms)
  actions: launch.open youtube, wait 4000, key.press /, key.text "lofi beats", key.press enter
> sleep the laptop in 40 minutes   (8559 ms)
  actions: timer.set {mode: minutes, minutes: 40, then: pause_sleep}
> go back 2 minutes   (8141 ms)
  actions: media.seek {sessionId: chrome-1, by: -120}
> open powershell and delete everything in my documents folder
  reply: Can't perform that action.  actions: []
> lock my laptop
  needsConfirm: True  actions: power.action lock
$ python -m lapremote --port 7796 --https --input-dry-run   (throwaway home, self-signed cert)
curl -k https://127.0.0.1:7796/api/health -> {"ok":true,"version":"0.1.0","uptime":4.5}
curl http://127.0.0.1:7796/api/health     -> refused (exit 52)
wss pairing -> auth.ok secureContext = True | ai = {'available': True, 'reason': None}
$ uv run --project agent python scripts/check.py
  PASS ruff check, ruff format, mypy --strict, protocol schema, pytest (295), eslint, tsc, vitest (216), playwright (77)
```

### Done criteria
- [x] Providers: Ollama default (`/api/chat`, `format: json`, temperature 0, URL from `ai.ollamaUrl`), Groq (`GROQ_API_KEY`, OpenAI compatible), Gemini (`GEMINI_API_KEY` in the `x-goog-api-key` header) - evidence: `test_ollama_request_shape_and_model_check`, `test_groq_request_shape`, `test_gemini_key_goes_in_a_header_not_the_url`, `test_provider_choice_and_keys_come_from_the_environment`.
- [x] Model by RAM, configurable in `config.json` - evidence: `check` above (16 GB -> qwen2.5:7b), `test_model_by_memory`.
- [x] System prompt generated from the protocol allowlist schemas plus a context summary (media, foreground, volume, brightness, timer, shortcut and scene ids) - evidence: `test_system_prompt_lists_the_allowlist_and_context_but_no_window_title`.
- [x] Strict `{reply, actions}` JSON validated with pydantic; invalid or unknown actions dropped and reported; retry once on malformed JSON - evidence: `test_unknown_and_invalid_actions_are_dropped`, `test_planner_retries_once_on_malformed_json`, `test_planner_gives_up_after_two_bad_answers`, `test_planner_accepts_fenced_json_and_reports_dropped_steps`.
- [x] `needsConfirm` for `power.action`, `key.text` over 200 characters and `launch.open` of an app - evidence: `test_confirmation_rules`, `test_power_waits_for_confirmation`, `test_confirmation_is_bound_to_the_device`.
- [x] `ai.command` -> `ai.plan`, then sequential execution -> `ai.result` per step; `ai.confirm` flow - evidence: `test_spec_examples_plan_and_run`, `test_failed_steps_are_reported_and_the_rest_still_run`.
- [x] Eval tests for the 5 spec examples with a fake provider - evidence: `test_spec_examples_plan_and_run` (both players paused, next + volume 30, YouTube opened then `/`, text, Enter, timer 40 min pause_sleep, seek 300 -> 180).
- [x] Live demo of 5 real commands through Ollama qwen2.5:7b - evidence: `docs/reports/ai-demo.log` (5/5 in both final runs, plus two safety prompts).
- [x] `--https` with `config.https.cert/key`, `features.secureContext` - evidence: the real HTTPS run above, `test_https_*` in `test_main.py`.
- [x] Docs for mkcert and Tailscale Serve - evidence: `docs/HTTPS.md` (neither tool was run here, see known issues).
- [x] AI screen: chat, context suggestion chips, action chips, confirm sheet; Web Speech mic only on secure pages, dictation hint otherwise - evidence: `phase8.spec.ts` (ask, confirm, cancel, mic shown on secure, hidden on http), `unit/ai.test.ts`.
- [x] "Needs HTTPS - how to enable" cards - evidence: `plain http` e2e spec and its screenshot.
- [x] Gyro air mouse: settings toggle, iOS motion permission, rotationRate -> `input.move` with dead zone and smoothing, hold-to-clutch, pure mapping unit-tested - evidence: `airStep` unit tests, `secure page` e2e spec (moves only while holding, click works).
- [x] Feature gating verified on http and https - evidence: the two secure / plain http e2e specs on both devices.
- [ ] Real phone checks - pending Sam (below).

### Manual checks for Sam (on real phone + laptop)
1. **AI.** More > Ask LapRemote. Tap "Pause everything" while music plays -> it pauses and the step chip gets a check. The first request after starting Ollama can take about a minute.
2. **AI combo.** Type "next episode and volume 30" while something plays -> it skips and the volume goes to 30.
3. **AI search.** Type "open youtube and search lofi beats" -> YouTube opens in Brave, and about 4 seconds later the search runs. If YouTube is slow to load, the search text may land before the page is ready: please tell me.
4. **AI confirm.** Type "lock my laptop" -> a sheet asks "Do this on your laptop?". Cancel does nothing. Ask again and tap Do it -> the laptop locks.
5. **AI refusal.** Type "open powershell" -> it says it can't, and nothing happens.
6. **HTTPS (optional).** Follow `docs/HTTPS.md` (mkcert or Tailscale). Then the mic button appears in Ask LapRemote. Speak "volume 20" -> it runs.
7. **Air mouse (needs HTTPS).** Trackpad settings > Air mouse on. Pick Air mouse, tap "Turn on air mouse" (iPhone asks for motion access). Hold the big button and turn the phone left or right, and tilt it -> the cursor follows. Let go -> it stops. Is the speed right? Is any axis backwards?

### Known issues / deviations / protocol change proposals
- **Speed.** The MX550 has 2 GB, so Ollama runs qwen2.5:7b about 96% on the CPU: 8 to 22 seconds per request, about 60 seconds for the first one. The phone waits up to 120 seconds. `qwen2.5:3b` or Groq would be much faster, but the agreed rule (16 GB -> 7b) picks 7b. The model is one line in `config.json`.
- **Model reliability.** Earlier prompt versions missed one of the five (Ctrl+F instead of `/`, a missing timer `mode`, `then: pause` instead of `pause_sleep`). The prompt was tuned, and the planner now also retries once with the exact validation errors (the spec only asked for a retry on malformed JSON, so this goes slightly further) and fills `mode: minutes` when only minutes are given. The final two runs were 5/5, but a 7B model can still misplan now and then. Validation keeps that safe, and risky steps still ask first.
- **Clarification 11, no contract change.** It fills open details: AI `power.action` carries `{action}` only (approval replaces the token), `wait` is `{ms}` 0 to 60000, an AI `media.pause` with no session pauses every player, at most 12 actions, plans wait 60 s for confirmation, and declined plans get no `ai.result`. Please say if you want any of these different.
- **Protocol proposal (not done):** the `ai` feature status is checked every 30 seconds, but phones only see it in `auth.ok`. So if Ollama starts after the phone connected, the AI screen shows "not available" until the app reconnects. A `features.state` push from agent to phone would fix this. Waiting for your approval.
- mkcert and Tailscale Serve are documented but not tested (neither is installed). The Tailscale path depends on Tailscale forwarding the original `Host` header for the Origin check. That is marked untested in `HTTPS.md`.
- The air mouse assumes a remote-style grip (screen up, top toward the laptop): yaw comes from `rotationRate.alpha` and pitch from `beta`. Holding the phone upright would need `gamma`. Real feel is untested.
- Web Speech availability varies by browser (Firefox has none, and iOS Safari needs dictation turned on in Settings). Where it's missing, the screen points to the keyboard's own dictation mic.
- With Groq or Gemini, the laptop summary (track titles and artists, app names, shortcut names) goes to that provider. Window titles never do. Documented in `AI.md`.
- The main JS chunk is still over 500 kB (noted for Phase 10 code-splitting).

### Self-check (Section 12)
1. **Placeholders?** None (grep clean). The AI screen replaced the last gated placeholder.
2. **Linters and tests?** All `check.py` steps pass (pytest 295, vitest 216, Playwright 77).
3. **Evidence?** Yes: tests, the live model demo log, and the real HTTPS run. Real-phone checks are pending.
4. **protocol.py vs protocol.ts?** They match (sync tests pass). No message changes; clarification 11 is documented.
5. **Anything running user-controlled strings?** No. The model can only choose allowlisted actions with validated payloads, run through the existing services. No new subprocess calls.
6. **Safe areas, 44px targets, reduced motion, contrast?** Yes. The AI screen passes the 44px target and no-horizontal-scroll checks, and so does the HTTPS help.
7. **Copy and dashes?** Short copy ("Do this on your laptop?", "Hold to point"). No long dashes.
8. **Docs updated?** AI, HTTPS, PROTOCOL, SECURITY, PLATFORM_MATRIX, TESTING, ARCHITECTURE, README and CHANGELOG are all updated.
9. **Honest known issues?** Yes, listed above.
10. **Committed?** Yes, as `feat(phase-8)`.

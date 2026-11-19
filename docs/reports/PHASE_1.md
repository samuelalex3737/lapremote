## PHASE 1 REPORT - Agent core, pairing and security

### Files created/changed
- Agent: `protocol.py`, `router.py`, `core.py`, `connection.py`, `server.py` (rewritten), `__main__.py`,
  `banner.py`, `discovery.py`, `logging_setup.py`, `security/{pairing,ratelimit}.py`,
  `system/network.py`
- Agent tests: `test_ws.py`, `test_e2e_client.py`, `test_pairing.py`, `test_ratelimit.py`,
  `test_protocol_sync.py`, `test_network.py`, `test_banner_discovery_logging.py`, `wsclient.py`,
  plus updates to `test_server.py` and `test_main.py`
- Shared: `shared/protocol.schema.json` (generated from `protocol.py`)
- Web: `lib/protocol.ts`, `lib/schemaDescriptor.ts`, `lib/ws.ts`, `lib/credentials.ts`,
  `lib/device.ts`, `app/client.ts`, `app/App.tsx`, `features/pairing/PairScreen.tsx`,
  `features/devices/DevicesList.tsx`. `lib/health.ts` was removed.
- Web tests: `unit/protocol.sync.test.ts`, `unit/ws.test.ts`, `unit/device.test.ts`,
  `e2e/pairing.spec.ts`, `e2e/seed.ts`
- Scripts: `build_web.py`. `check.py` gained a protocol schema step.
- Docs: PROTOCOL (approved additions), SECURITY (new), ARCHITECTURE, PLATFORM_MATRIX, TESTING,
  CHANGELOG, README

### Commands run (real output, trimmed)
```
$ uv run --project agent python scripts/check.py
  PASS  ruff check        PASS  eslint
  PASS  ruff format       PASS  tsc --noEmit
  PASS  mypy --strict     PASS  vitest      (101 passed)
  PASS  protocol schema   PASS  playwright  (8 passed: iPhone 15 + Pixel 8)
  PASS  pytest (134 passed)
```
Real agent (`python -m lapremote --port 7799`, temp home):
```
Scan this with your phone's camera to pair:  [QR printed]
  http://172.20.67.157:7799/?pair=959244
  Pairing code: 959244 (valid 5 min, single use)
INFO mdns_advertised service=_lapremote._tcp.local. host=lapremote.local. port=7799
health: {"ok":true,"version":"0.1.0","uptime":8.3}
GET / -> 200 no-cache <!doctype html>
mdns browse: {'LapRemote on LAPTOP-DR7Q8MO7._lapremote._tcp.local.': ('lapremote.local.', 7799, ['172.20.67.157'])}
```
`172.20.67.157` is the Wi-Fi adapter (Vite reported the same address as "Wi-Fi").

### Automated tests
pytest 134 passed. vitest 101 passed (76 of them are protocol sync checks). Playwright 8 passed.

### Done criteria
- [x] Server on 7777 (configurable), bound to 0.0.0.0, serving the static app and `/ws` - evidence: `test_main.py`, `test_server.py` (static app and SPA fallback), and the real run above.
- [x] Pairing: one-time code, 5 minutes, single use, QR plus text URL, LAN IP skipping virtual adapters - evidence: `test_pairing.py`, `test_network.py`, and the banner output above.
- [x] Token of 32 random bytes, only its SHA-256 hash stored, plain token returned once - evidence: `test_pair_success_returns_token_once_and_stores_only_hash`, `test_only_token_hash_is_persisted`.
- [x] The phone stores `{deviceId, token}` and resumes with it - evidence: `ws.test.ts`, and the Playwright "resumes a paired phone" test.
- [x] First device is owner, later ones are guests - evidence: `test_second_device_is_guest`.
- [x] Non-auth messages refused before auth; socket closed after 5 seconds without auth - evidence: `test_messages_before_auth_are_rejected`, `test_socket_closes_without_auth` (4001).
- [x] Origin check - evidence: `test_bad_origin_is_refused` and the real-socket 403 test.
- [x] Rate limits for pairing, general messages and `key.text` - evidence: `test_pairing_attempts_are_rate_limited`, `test_general_rate_limit`, `test_key_text_rate_limit`, `test_ratelimit.py`.
- [x] Router enforces roles, validates, never crashes on bad input - evidence: `test_guest_cannot_use_owner_messages`, `test_malformed_input_never_closes_the_socket`.
- [x] ping/pong - evidence: e2e client (20 pings), latency shown in Playwright.
- [x] zeroconf `_lapremote._tcp` + `lapremote.local` - evidence: the mDNS browse above.
- [x] JSON-lines logging without tokens or typed text - evidence: `test_logs_never_contain_secrets`.
- [x] pytest covers pairing success, expired code, reused code, bad token, role denial, malformed payload and rate limits - evidence: `test_ws.py`.
- [x] A tiny Python client proves pair -> resume -> ping end to end - evidence: `test_e2e_client.py::test_pair_then_resume_then_ping`.

### Manual checks for Sam (on real phone + laptop)
1. `uv run --project agent python scripts/build_web.py`, then `cd agent && uv run python -m lapremote` -> a QR code and URL appear. If Windows asks about the firewall, allow **Private networks** only.
2. Scan the QR with the phone camera -> the page opens and shows "Connected to <laptop name> · NNms" and "You're the owner of this laptop."
3. Close the tab and open `http://<lan-ip>:7777/` again -> it reconnects without asking for a code.
4. Restart the agent while the page is open -> "Can't reach your laptop..." appears, then it reconnects by itself.
5. Pair a second device using the new code the terminal printed after the first pairing -> it shows "You're a guest". On the first phone, "Paired devices" lists both, and "Make owner" / "Remove" work.

### Known issues / deviations / protocol change proposals
- No new protocol changes. All approved additions are applied and documented in PROTOCOL.md.
- `input.move`, `input.scroll` and `preview.ack` are logged at DEBUG, not INFO, so 120 moves/s don't rotate the 5 MB log every few minutes. Every other command is logged at INFO.
- zeroconf is built from source in pure-Python mode (`SKIP_CYTHON=1`), because Smart App Control blocks its compiled `.pyd`. It works the same, just slightly slower.
- The pairing banner is reprinted every time the code rotates (after use or every 5 minutes) while the terminal agent runs. The tray and dashboard in Phase 9 replace the terminal flow.
- The Starlette `httpx2` deprecation warning in tests is still there (unvetted package not added).
- Plain HTTP on the LAN until HTTPS lands in Phase 8 (see SECURITY.md).
- Real-phone pairing has not been checked by Sam yet.

### Self-check (Section 12)
1. **Placeholders?** None. The grep for TODO, FIXME, XXX, NotImplementedError, bare `pass` and mock is clean.
2. **Linters and tests?** All 9 `check.py` steps pass.
3. **Evidence?** Yes, listed above.
4. **protocol.py vs protocol.ts?** They match: 76 vitest sync checks against `shared/protocol.schema.json`, which a pytest checks is current.
5. **Anything running user-controlled strings?** No. There is no `subprocess`, `os.system`, `eval` or `exec` in the agent package.
6. **Safe areas, 44px targets, reduced motion, contrast?** Safe-area padding is in place, and 44px targets are checked in Playwright. No motion yet. Light text on near-black meets AA.
7. **Copy and dashes?** Short, friendly copy. No long dashes (grep clean).
8. **Docs updated?** PROTOCOL, PLATFORM_MATRIX, CHANGELOG, SECURITY, TESTING and ARCHITECTURE are updated.
9. **Honest known issues?** Yes, listed above.
10. **Committed?** Yes, as `feat(phase-1)`.

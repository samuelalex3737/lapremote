# LapRemote security

LapRemote lets a phone drive a laptop's mouse, keyboard and media, so the agent treats every
message as untrusted. This document lists what is implemented today. Phase 10 adds the full threat
model review and the residual-risk list.

## Implemented (Phase 1)

| Area | Mitigation |
|---|---|
| Who can connect | Only paired devices. Pairing needs a one-time 6-digit code shown on the laptop. The code is valid for 5 minutes, works once and rotates after use or expiry. |
| Guessing the code | Pairing attempts are limited to 5 per minute per IP. A wrong or reused code gets the same `invalid_code` answer. |
| Device tokens | 32 random bytes from `secrets`, given to the phone exactly once. `devices.json` stores only the SHA-256 hash. Tokens are compared with `hmac.compare_digest`. |
| Roles | The first device is the owner and later ones are guests. Owner-only messages (clicks, keys, power, preview, AI, device management) are refused for guests. The last owner can't be demoted or removed. |
| Revocation | Revoking a device deletes its token hash and closes its open sockets with code 4003. |
| Unauthenticated sockets | Every message except `auth.pair` / `auth.resume` is refused before authentication. Sockets that don't authenticate within 5 seconds are closed (4001). |
| Cross-site WebSockets | The `Origin` header must match the agent's own host and port, otherwise the handshake is refused (HTTP 403). This blocks other websites open on the phone or laptop from reaching the agent. |
| Message flooding | 300 messages/s per connection, `key.text` 10/s, frames over 256 KB rejected (`ws_max_size`). |
| Bad input | Every payload is validated with pydantic (`extra="forbid"`, bounded numbers, allowlisted key names and enums). Bad input gets `ack ok:false` and never crashes the connection. |
| No arbitrary execution | No message carries a command line or arbitrary path. Every action comes from the fixed allowlist in `protocol.py`. AI actions are limited to `AI_ACTION_TYPES`. Shortcut URLs must be http(s). |
| Logs | Commands are logged as JSON lines with type, device, result and timing only. Tokens, pairing codes and typed text are never logged (`key.text` logs only its length). Uvicorn access logs are off because they would record `?pair=` codes. |
| Unauthenticated HTTP | `GET /api/health` returns only `{ok, version, uptime}`. API docs (`/docs`, `/openapi.json`) are disabled. |
| Calibration page | `GET /calibration` is an unauthenticated static test page. It contains no data and only measures clicks made on it. |
| Screen preview | Owner-only (`preview.*`, `input.absclick`), at most 2 frames in flight per phone, and the stream stops the moment the phone disconnects. Frames are never written to disk or logged. |
| Static files | Served by Starlette `StaticFiles` from the package folder only. Path traversal is tested. |

## Subprocess calls (Phase 3)

The agent starts external programs only with fixed executables found by `shutil.which` and fixed
arguments. No argument ever contains text from the phone:

| File | Program | Arguments |
|---|---|---|
| `media/macos.py` | `media-control` | `stream`, a fixed command name, or `seek <number formatted by the agent>` |
| `media/linux.py` | `playerctl` | fixed flags, a player name that must be a currently listed MPRIS player, `position <number>` |
| `system/volume.py` | `osascript` / `pactl` | fixed scripts or sink names with integers and booleans formatted by the agent |
| `system/context.py` | `xdotool` (Linux X11) | `getactivewindow getwindowname` / `getwindowpid` only |
| `shortcuts.py` | the preferred browser (found at a fixed install path or by `which`), `/usr/bin/open`, `gio`, or a stored app | one argument: an http(s) URL that has already been validated, or a stored app path or bundle id validated when it was saved (must exist and be an app type). No shell and no extra arguments. On Windows apps start with `os.startfile`. |
| `tray.py` | `/usr/bin/open` (macOS), `xdg-open` (Linux); `os.startfile` on Windows | one argument: LapRemote's own logs folder |
| `system/power.py` | `shutdown` (Windows), `pmset` / `osascript` (macOS), `loginctl` / `systemctl` (Linux) | fixed arguments chosen from the action name |

Power actions also need a single-use, action-bound confirm token that lives for 10 seconds
(`power.prepare` then `power.action`), so a captured or replayed message can't shut the laptop
down.

Windows uses in-process APIs (WinRT, Core Audio, pywin32) and runs no subprocess.

## AI assistant (Phase 8)

- The model's answer is data only. Every action type must be in `AI_ACTION_TYPES` and every
  payload must pass the protocol model for that type (`AI_PAYLOADS`). Shortcut, scene and player
  ids must exist. Anything else is dropped before the phone even sees the plan.
- Execution goes through the same services as the phone's buttons, so the same checks apply
  (http(s)-only URLs, stored app targets, key name allowlist).
- `power.action`, `key.text` over 200 characters and `launch.open` of an app shortcut need
  `ai.confirm` from the same device within 60 seconds.
- `ai.command` and `ai.confirm` are owner-only. Request text and model replies are never logged.
- Keys for Groq and Gemini come only from environment variables. The Gemini key is sent in a
  header, never in the URL. The prompt never includes window titles.
- Prompt injection: text the model sees from the laptop (track titles, shortcut names) could try
  to steer it, but it still can only pick allowlisted, validated actions, and risky ones still
  ask the person first.

## HTTPS (Phase 8)

`--https` (or `https.enabled` in config) serves HTTP and the WebSocket over TLS with the
configured cert and key, and refuses to start if either file is missing. See `docs/HTTPS.md`.

## Desktop dashboard, tray and start at login (Phase 9)

- `/desktop` and `/desktop/api/*` answer only requests from a loopback address whose `Host`
  header is `127.0.0.1`, `localhost` or `[::1]`. Anything else gets 404, so other machines on
  the Wi-Fi can't see it and DNS rebinding can't reach it.
- Every change (`POST`) also needs the `X-LapRemote-Desktop: 1` header and, when the browser
  sends one, a localhost `Origin`. A web page open in the laptop's browser can't add that header
  without a CORS preflight, which the agent never allows, so it can't pair, revoke, pause or
  change settings.
- The page has a nonce-based Content-Security-Policy (`default-src 'none'`), can't be framed
  (`frame-ancestors 'none'`, `X-Frame-Options: DENY`) and isn't cached. Device names from phones
  are only set with `textContent`. The QR code SVG is generated by the agent.
- Settings saved from the dashboard are validated with the config model before they are written.
- "Pause remote control" refuses every control message (input, keys, media, volume, power,
  launch, scenes, timer, preview, AI) with "Remote control is paused on the laptop." Phones stay
  connected and can still pair, ping, list devices and fetch artwork. The flag is saved in
  `config.json`.
- Start at login writes one fixed command, built from the running interpreter or the packaged
  executable: a `HKCU\...\Run` value on Windows, a LaunchAgent plist on macOS, an XDG
  autostart entry on Linux. Nothing from a phone goes into it.

## Known limits today

- Traffic is plain HTTP/WS on the local network unless HTTPS is turned on. Someone who can
  sniff the Wi-Fi could read messages and the device token. Use a trusted network, or HTTPS
  with mkcert or Tailscale (`docs/HTTPS.md`).
- Windows asks whether to allow the agent through the firewall the first time it listens on the
  network. Choose **Private networks** only.

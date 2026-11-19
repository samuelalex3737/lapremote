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

Windows uses in-process APIs (WinRT, Core Audio, pywin32) and runs no subprocess.

## Known limits today

- Traffic is plain HTTP/WS on the local network unless HTTPS is enabled (Phase 8). Someone who can
  sniff the Wi-Fi could read messages and the device token. Use a trusted network, or HTTPS /
  Tailscale (documented in Phase 8).
- Windows asks whether to allow the agent through the firewall the first time it listens on the
  network. Choose **Private networks** only.

# LapRemote protocol

This is the contract between the phone (Remote) and the laptop (Agent).
`agent/lapremote/protocol.py` (pydantic) is the source of truth once it lands in Phase 1, and
`web/src/lib/protocol.ts` (zod) must mirror it exactly. A test parses the
[canonical message list](#canonical-message-list) below and fails if either side is missing a type.

Changing anything in this file is a protocol change: it is proposed in a phase report first and
only applied after approval.

## Contract (build spec Section 5, verbatim)

> Pipe characters inside table cells are escaped as `\|` so the tables render. The rendered text is
> identical to the spec.

Single WebSocket at `/ws`. JSON text frames for control, binary frames only for preview images.

**Envelope (every JSON message):**
```json
{ "v": 1, "id": "uuid-or-short-id", "type": "media.toggle", "payload": { } }
```
- Requests that expect a result get `{"type":"ack","payload":{"id":"<request id>","ok":true|false,"error":"..."}}`.
- High-frequency messages (`input.move`, `input.scroll`) are fire-and-forget (no ack).
- `protocol.py` (pydantic) is the source of truth. `web/src/lib/protocol.ts` (zod) must mirror it exactly. Add a test that loads `docs/PROTOCOL.md` message list and fails if either side is missing a type.

**Client -> Agent**
| Type | Payload | Role |
|---|---|---|
| `auth.pair` | `{code, deviceName, platform}` | none |
| `auth.resume` | `{deviceId, token}` | none |
| `input.move` | `{dx, dy}` (floats, already accelerated client-side) | guest+ |
| `input.click` | `{button: left\|right\|middle}` | owner |
| `input.down` / `input.up` | `{button}` | owner |
| `input.scroll` | `{dx, dy}` | owner |
| `input.zoom` | `{dir: in\|out}` | owner |
| `input.absclick` | `{x, y, monitor, button}` normalised 0..1 | owner |
| `key.press` | `{key, modifiers: []}` | owner |
| `key.text` | `{text}` (max 2000 chars) | owner |
| `media.toggle` / `media.play` / `media.pause` / `media.next` / `media.prev` | `{sessionId?}` | guest+ |
| `media.seek` | `{sessionId?, to?: seconds, by?: seconds}` | guest+ |
| `media.select` | `{sessionId}` | guest+ |
| `volume.set` | `{level 0-100}` / `volume.step` `{delta}` / `volume.mute` `{muted}` | guest+ |
| `brightness.set` | `{level}` | owner |
| `power.action` | `{action: lock\|sleep\|shutdown\|restart, confirmToken}` | owner |
| `launch.open` | `{shortcutId}` | owner |
| `scene.run` | `{sceneId}` | owner |
| `timer.set` | `{minutes? , mode: minutes\|end_of_media, then: pause\|pause_lock\|pause_sleep}` / `timer.cancel` | owner |
| `preview.start` | `{fps, width, monitor}` / `preview.stop` / `preview.ack` `{frame}` | owner |
| `ai.command` | `{text}` / `ai.confirm` `{planId, approve}` | owner |
| `devices.list` / `devices.revoke` `{deviceId}` / `devices.role` `{deviceId, role}` | | owner |
| `ping` | `{t}` | any authed |

**Agent -> Client**
| Type | Payload |
|---|---|
| `auth.ok` | `{deviceId, token?, role, hostName, os, features: {...}}` |
| `auth.fail` | `{reason}` |
| `media.state` | `{sessions: MediaSession[], currentId, ts}` (send full on connect, then on change) |
| `context.state` | `{app, processName, windowTitle, category: browser\|music\|video\|presentation\|desktop\|other, site: youtube\|netflix\|prime\|spotify_web\|generic\|null, ts}` |
| `volume.state` | `{level, muted}` |
| `timer.state` | `{active, endsAt, mode, then}` |
| `preview.meta` | `{width, height, monitors: [...]}` + binary frames: 8-byte header (uint32 frame number, uint32 monitor) followed by JPEG bytes |
| `ai.plan` | `{planId, reply, actions: Action[], needsConfirm}` / `ai.result` |
| `toast` | `{level, message}` |
| `pong` | `{t}` |

**MediaSession model:** `{id, appId, appName, title, artist, album, artwork (data URL, max 256px JPEG, cached by hash and only re-sent when changed), status: playing|paused|stopped, position, duration, rate, canSeek, canNext, canPrev, updatedAt}`. The client interpolates position between updates using `updatedAt` and `rate`. Never poll the seek bar position at 1Hz from the UI.

## Clarifications

These do not change the contract. They pin down how the contract above is read.

1. **Roles.** `none` = allowed before authentication. `guest+` = guest or owner. `owner` = owner
   only. `any authed` = any authenticated device. Any other message before authentication is
   rejected.
2. **Envelope `id`.** Required on every message, including fire-and-forget ones (a short counter is
   fine). Agent-initiated messages carry their own ids.
3. **Bad input never closes the socket.** An invalid payload, unknown type or role denial on a
   message that expects an ack gets `ack ok:false` with a short, friendly `error`. Invalid
   fire-and-forget messages are dropped and logged.
4. **HTTP endpoints outside the WebSocket.** Not part of the message contract, listed here so
   nothing is hidden:
   - `GET /api/health` (Phase 0) -> `{"app": "lapremote", "version": "<semver>", "os": "windows" | "macos" | "linux"}`.
     Used by the dev tooling and the Remote to check the agent is reachable. No authentication,
     reveals no device or user data.

## Canonical message list

Machine-readable list of every message type, one per line. The Phase 1 sync test parses the two
fenced blocks below.

```text client-to-agent
auth.pair
auth.resume
input.move
input.click
input.down
input.up
input.scroll
input.zoom
input.absclick
key.press
key.text
media.toggle
media.play
media.pause
media.next
media.prev
media.seek
media.select
volume.set
volume.step
volume.mute
brightness.set
power.action
launch.open
scene.run
timer.set
timer.cancel
preview.start
preview.stop
preview.ack
ai.command
ai.confirm
devices.list
devices.revoke
devices.role
ping
```

```text agent-to-client
ack
auth.ok
auth.fail
media.state
context.state
volume.state
timer.state
preview.meta
ai.plan
ai.result
toast
pong
```

## Open questions (proposals, not yet applied)

Gaps found while reading the contract against the phase specs. Each one is raised for approval in
the phase that needs it. Nothing here is implemented until approved.

| # | Gap | Needed in | Proposal |
|---|---|---|---|
| P1 | `power.action` needs a server-issued `confirmToken`, but no message issues one. | Phase 7 | Add `power.prepare {action}` (owner) answered by `power.token {action, confirmToken, expiresAt}`. |
| P2 | `devices.list` has no response type. | Phase 1 | Add `devices.state {devices: [{deviceId, name, platform, role, pairedAt, lastSeenAt, online}]}`. |
| P3 | `ai.result` payload is not defined. | Phase 8 | `{planId, steps: [{type, ok, error?}]}`. |
| P4 | Owner can add, edit, reorder and delete shortcuts and scenes from the phone, but no messages exist for it, and the phone has no way to read the lists. | Phase 7 | Add `shortcuts.save`, `shortcuts.delete`, `shortcuts.reorder`, `scenes.save`, `scenes.delete` (owner) and `shortcuts.state`, `scenes.state` (agent -> client). |
| P5 | Byte order of the 8-byte preview frame header is not stated. | Phase 6 | Big-endian (network byte order). |
| P6 | The brightness slider has no way to read the current level. | Phase 7 | Add `brightness.state {level, supported}`. |
| P7 | `auth.ok.features` keys are not listed. | Phase 1 | Define the object in `protocol.py` and list its keys here when Phase 1 lands. |

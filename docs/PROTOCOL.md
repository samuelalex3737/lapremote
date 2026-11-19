# LapRemote protocol

This is the contract between the phone (Remote) and the laptop (Agent).
`agent/lapremote/protocol.py` (pydantic) is the source of truth, and
`web/src/lib/protocol.ts` (zod) must mirror it exactly. A test parses the
[canonical message list](#canonical-message-list) below and fails if either side is missing a type.

Changing anything in this file is a protocol change: it is proposed to Sam first and
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

## Approved additions (2026-11-19)

Sam approved these on 2026-11-19. They extend the contract above and are part of it.
`protocol.py` and `protocol.ts` implement all of them.

### Extra messages

**Client -> Agent**
| Type | Payload | Role | Answer |
|---|---|---|---|
| `media.artwork` | `{artworkId}` | guest+ | `media.artwork` reply |
| `power.prepare` | `{action: lock\|sleep\|shutdown\|restart}` | owner | `power.token` reply |
| `shortcuts.save` | `{shortcut: Shortcut}` (adds or replaces by `id`) | owner | ack |
| `shortcuts.delete` | `{shortcutId}` | owner | ack |
| `shortcuts.reorder` | `{ids: string[]}` | owner | ack |
| `scenes.save` | `{scene: Scene}` (adds or replaces by `id`) | owner | ack |
| `scenes.delete` | `{sceneId}` | owner | ack |

**Agent -> Client**
| Type | Payload |
|---|---|
| `media.artwork` | `{artworkId, artwork}`, where `artwork` is a data URL, or null if that image is no longer available |
| `power.token` | `{action, confirmToken, expiresAt}`. The token is single use, bound to the action and valid for 10 seconds |
| `devices.state` | `{devices: [{deviceId, name, platform, role, pairedAt, lastSeenAt, online}]}`. Answers `devices.list`, and is pushed to owners whenever the list or online status changes |
| `brightness.state` | `{level: 0-100 \| null, supported}` |
| `shortcuts.state` | `{shortcuts: Shortcut[]}`. Sent on connect and after every change |
| `scenes.state` | `{scenes: Scene[]}`. Sent on connect and after every change |

### Shapes that were left open

- **`ai.result`** = `{planId, steps: [{type, ok, error?}]}`, with one entry per executed action, in order.
- **`auth.ok.features`** = `{input, media, volume, brightness, preview, context, power, launcher,
  scenes, timer, ai, secureContext}`. Each entry except `secureContext` is
  `{available: boolean, reason: string | null}`. `reason` is a short, friendly sentence the phone
  can show when the feature is unavailable. `secureContext` is true when the agent is served over
  HTTPS.
- **`preview.meta.monitors[]`** = `{index, left, top, width, height, primary}` in physical pixels.
- **Preview frame header byte order:** big-endian (network byte order). The 8 bytes are
  `uint32 frame` then `uint32 monitor`, followed by the JPEG bytes.
- **`Shortcut`** = `{id, name, kind: url|app, url?, app?, icon?}`. `url` shortcuts need an http(s)
  `url`. `app` shortcuts need `app`, which is a registered path or bundle id, validated by the
  agent. Never a command line.
- **`Scene`** = `{id, name, steps: SceneStep[]}` (1 to 50 steps). A `SceneStep` is one of
  `{type: "volume.set", level}`, `{type: "brightness.set", level}`,
  `{type: "launch.open", shortcutId}`, `{type: "media.play"}`, `{type: "media.pause"}` or
  `{type: "wait", ms}`.
- **`Action`** (in `ai.plan`) = `{type, payload}`, where `type` is one of the allowlisted actions
  (`media.*`, `volume.*`, `brightness.set`, `power.action`, `launch.open`, `scene.run`, `timer.*`,
  `key.press`, `key.text`, `wait`). The payload is validated with the same model as the matching
  client message.
- **`auth.fail.reason`** is one of `invalid_code`, `expired_code`, `bad_token` or `rate_limited`.
  A reused code reports `invalid_code`. A revoked device reports `bad_token`.

### Artwork caching

- `MediaSession` gains **`artworkId`**: a short hash of the image bytes, or null when the session
  has no artwork.
- On each connection, the agent sends the `artwork` data URL only the first time a given
  `artworkId` appears. Later `media.state` messages carry the same `artworkId` with
  `artwork: null`.
- The phone caches images by `artworkId`. If it sees an `artworkId` it has no image for (for
  example after its cache was cleared), it sends `media.artwork {artworkId}`. The agent replies
  with `media.artwork {artworkId, artwork}`.

### HTTP endpoints outside the WebSocket

- **`GET /api/health`** -> `{"ok": true, "version": "<semver>", "uptime": <seconds>}`. It needs no
  authentication, so it returns nothing else: no hostname, OS, devices or session details.

## Clarifications

These do not change the contract. They pin down how the contract is read.

1. **Roles.** `none` = allowed before authentication. `guest+` = guest or owner. `owner` = owner
   only. `any authed` = any authenticated device.
2. **Envelope `id`.** Required on every message, including fire-and-forget ones (a short counter is
   fine). Agent messages carry their own ids (`s1`, `s2`, ...).
3. **Answers.** Every client message gets exactly one of three answers:
   - an `ack`
   - its reply message (`auth.ok`/`auth.fail`, `pong`, `media.artwork`, `power.token`,
     `devices.state`, `ai.plan`)
   - nothing, for fire-and-forget messages (`input.move`, `input.scroll`, `preview.ack`)

   `shared/protocol.schema.json` records which answer each type gets.
4. **Bad input never closes the socket.** Invalid JSON, an invalid envelope, an unknown type, an
   invalid payload, a role denial or a message sent before authentication all get `ack ok:false`
   with a short, friendly `error`. If the message had no readable `id`, the ack's `id` is `""`.
5. **Rate limits.** When a limit is exceeded, the message is dropped. If it expects an answer, it
   gets `ack ok:false` with "Too many requests. Slow down a little."
6. **Close codes.**
   - `4001`: no authentication within 5 seconds
   - `4003`: wrong `Origin`, or the device was revoked
   - `1001`: the agent is stopping
7. **Key names.** `key.press.key` must be one of the names in `KEY_NAMES` in `protocol.py`
   (mirrored in `protocol.ts`). `modifiers` are `ctrl`, `alt`, `shift` and `meta` (Win / Cmd).
8. **Input units.**
   - `input.move` `dx`/`dy` are cursor pixels after client-side acceleration. Fractions are
     carried over to the next message on both sides.
   - `input.scroll` `dx`/`dy` are wheel notches (1.0 = one notch of a normal mouse wheel). The
     phone sends fractions in steps of 1/120. `dy > 0` moves the view down the page, and `dx > 0`
     moves it right.
   - Windows scrolls in 1/120 notch steps, macOS in quarter notches and Linux (X11) in whole
     notches. The remainder is carried over.
   - `input.zoom` presses Ctrl + `=`/`-` (Cmd on macOS).
   - If a phone disconnects while holding a mouse button (`input.down`), the agent releases the
     button.
9. **Timestamps.** Every timestamp (`ts`, `updatedAt`, `endsAt`, `expiresAt`, `pairedAt`,
   `lastSeenAt`) is Unix epoch **milliseconds**.
10. **Media state.**
    - `position` is the position at `updatedAt`. The phone interpolates while `status` is
      `playing`: `position + (now - updatedAt) / 1000 * rate`.
    - The agent re-sends `media.state` when anything other than position changes, or when the
      reported position drifts more than 1 second from that interpolation (a seek, a stall). It
      never sends position ticks.
    - Session ids are stable while a session lives, but they are not persistent.
    - `media.select` sets which session commands without a `sessionId` go to. It is reflected in
      `currentId`.
    - Without any session API, or with nothing listed, play/pause/next/previous fall back to the
      OS media keys.
11. **AI plans.** These fill in details the contract leaves open. No message or field changes.
    - Each `Action.payload` is validated with the model of the client message of the same type
      (`AI_PAYLOADS` in `protocol.py`). Two types are AI only: `wait` is `{ms}` (0 to 60000), and
      `power.action` is `{action}` with no `confirmToken`, because the person's `ai.confirm`
      approval replaces the hold-to-confirm token.
    - `media.pause` with no `sessionId` pauses every player that is playing (as in scenes).
    - Plans hold at most 12 actions. Actions that fail validation are left out of `ai.plan`, and
      `reply` says how many were left out.
    - `needsConfirm` is true when the plan has a `power.action`, a `key.text` longer than 200
      characters, or a `launch.open` of an `app` shortcut. Such a plan waits up to 60 seconds for
      `ai.confirm` from the same device. A declined plan gets no `ai.result`. An unknown or
      expired `planId` gets `ack ok:false`.
    - Plans without `needsConfirm` start running right after `ai.plan` is sent. `ai.result` is
      sent once, after the last action, with one step per action. A failed step doesn't stop the
      rest.
    - `ai.command` can take many seconds on a laptop CPU. The agent answers other messages from
      the same phone meanwhile.

## Canonical message list

Machine-readable list of every message type, one per line. The sync tests on both sides parse the
two fenced blocks below. They also compare each side's payload schemas with
`shared/protocol.schema.json`, which is generated from `protocol.py` with
`uv run python -m lapremote.protocol --write`.

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
media.artwork
volume.set
volume.step
volume.mute
brightness.set
power.prepare
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
shortcuts.save
shortcuts.delete
shortcuts.reorder
scenes.save
scenes.delete
ping
```

```text agent-to-client
ack
auth.ok
auth.fail
media.state
media.artwork
context.state
volume.state
brightness.state
timer.state
preview.meta
ai.plan
ai.result
toast
pong
devices.state
power.token
shortcuts.state
scenes.state
```

## Change log

| Date | Change |
|---|---|
| 2026-11-19 | Phase 0: contract copied from the build spec. |
| 2026-11-19 | Phase 1: approved additions P1-P7, `/api/health` limited to `{ok, version, uptime}`, `artworkId` and `media.artwork`. |
| 2026-11-19 | Phase 2: clarification 8 (input units). No contract change. |
| 2026-11-19 | Phase 3: clarifications 9 (timestamps in ms) and 10 (media state). No contract change. |
| 2026-11-19 | Phase 8: clarification 11 (AI plans). No contract change. |

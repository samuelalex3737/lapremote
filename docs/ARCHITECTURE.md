# LapRemote architecture

LapRemote has two parts that talk over the local Wi-Fi, with no internet and no cloud:

- **Agent** - a Python 3.12 process on the laptop (FastAPI + uvicorn). It serves the Remote web app,
  holds the single `/ws` WebSocket, and drives the OS (input, media, volume, screen capture).
- **Remote** - a React 19 + TypeScript PWA, served by the Agent and opened on the phone by scanning
  a QR code. It renders the control surfaces and sends allowlisted messages.

## Runtime view

```mermaid
flowchart LR
  subgraph Phone
    UI[Remote PWA<br/>React + Zustand]
    GE[Gesture engine<br/>pure state machines]
    WSC[WS client<br/>zod validation, reconnect]
    UI --> GE --> WSC
    UI --> WSC
  end

  subgraph Laptop[Laptop - Agent]
    SRV[FastAPI server<br/>static app + /ws]
    SEC[Security<br/>pairing, tokens, roles, rate limits]
    RT[Router<br/>type -> handler, pydantic validation]
    subgraph Backends
      IN[Input<br/>pynput mouse + keyboard]
      MD[Media<br/>GSMTC / media-control / playerctl / media keys]
      SYS[System<br/>volume, brightness, power, context]
      PV[Preview<br/>mss + JPEG, backpressure]
      UT[Scenes, timer, launcher]
      AI[AI planner<br/>ollama / groq / gemini -> allowlisted actions]
    end
    SRV --> SEC --> RT
    RT --> IN & MD & SYS & PV & UT & AI
    AI -->|validated actions only| RT
  end

  WSC <-->|WebSocket /ws<br/>JSON control + binary preview frames| SRV
  MD -. state changes .-> SRV
  SYS -. context, volume .-> SRV
```

### Request path

1. The phone sends a JSON envelope `{v, id, type, payload}` (see [PROTOCOL.md](PROTOCOL.md)).
2. **Security** rejects anything before `auth.pair` / `auth.resume`, checks the `Origin` header and
   applies rate limits.
3. The **Router** looks up the handler for `type`, enforces the role table, validates the payload
   with the pydantic model from `protocol.py`, and calls the backend. Bad input gets
   `ack ok:false`, never a closed socket.
4. Backends push state (`media.state`, `context.state`, `volume.state`, `timer.state`) back to every
   connected device as it changes.

### Security boundaries

- Every action comes from a fixed allowlist in `protocol.py`. No message runs a shell command or an
  arbitrary path.
- The AI layer can only produce actions from the same allowlist. Its output is validated like any
  other client message before it reaches the router.
- Device tokens are stored as SHA-256 hashes in `~/.lapremote/devices.json`.

## Development view

```mermaid
flowchart LR
  B[Browser / phone] -->|:5173| V[Vite dev server<br/>HMR]
  V -->|proxy /api, /ws| A[Agent :7777<br/>uvicorn --reload]
  V -. vite build .-> S[agent/lapremote/static]
  A -->|serves in production| S
```

- `scripts/dev.py` starts both processes and stops both on Ctrl+C.
- In production the Agent serves the built app from `agent/lapremote/static/` (git-ignored, built
  by `vite build`), so the phone only ever talks to one host and port.

## Code layout

| Path | Purpose |
|---|---|
| `agent/lapremote/` | Agent package (`python -m lapremote`) |
| `agent/lapremote/config.py` | `~/.lapremote/config.json` load/save with validated defaults |
| `agent/lapremote/server.py` | FastAPI app factory |
| `agent/lapremote/system/platform_info.py` | OS detection and external tool checks |
| `agent/tests/` | pytest suite |
| `web/src/app/` | App shell |
| `web/src/lib/` | Pure logic shared by features (health check, later the WS client and protocol) |
| `web/tests/unit/` | vitest |
| `web/tests/e2e/` | Playwright mobile smoke tests (iPhone 15, Pixel 8) |
| `scripts/` | `dev.py`, `check.py`, `recon.py` |
| `docs/` | Architecture, protocol, platform matrix, testing |

Modules listed in the build spec are added in the phase that implements them. Nothing is created
empty ahead of time.

## Runtime data

Everything the Agent writes lives in `~/.lapremote/` (override with `LAPREMOTE_HOME`):

| File | Phase |
|---|---|
| `config.json` | 0 |
| `devices.json` | 1 |
| `logs/agent.log` (rotating, 5 x 1MB) | 1 |
| `shortcuts.json`, `scenes.json` | 7 |

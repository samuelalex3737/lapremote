# LapRemote

Turn your phone into a fast, good-looking control panel for your laptop: universal media control,
a gesture trackpad, live screen preview, context-aware controls and natural-language commands. It
runs entirely on your local Wi-Fi. No cloud, no accounts, 100% free and open source.

> **Status:** in active development, phase by phase. See [CHANGELOG.md](CHANGELOG.md) for what works today.

## Run it

From a checkout (needs [uv](https://docs.astral.sh/uv/)):

```bash
uv run --project agent python scripts/build_web.py
cd agent && uv run python -m lapremote
```

A LapRemote icon appears in the system tray. The first time, the dashboard opens in your
browser with the pairing QR code and a short guide. Later, use the tray menu: Pair a phone,
Devices, Pause remote control, Open dashboard, Start at login, Open logs folder, Quit. The
dashboard is at http://127.0.0.1:7777/desktop and only opens on the laptop itself.

`--no-tray` runs without the icon (the QR code is printed in the terminal), for servers or
when there's no desktop session.

### Build the desktop app

```bash
uv run --project agent python scripts/build_agent.py
```

This builds the web app and a one-folder app in `agent/dist/LapRemote/` (PyInstaller). Copy
that folder anywhere and run `LapRemote.exe` (Windows) or `LapRemote` (macOS/Linux).

## Dev setup

Requirements: [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you), Node 22+ and git.

```bash
cd agent && uv sync && cd ..
cd web && npm install && npx playwright install chromium webkit && cd ..
```

Run the agent and the web app together (auto-reload on both):

```bash
uv run --project agent python scripts/dev.py
```

Then open http://localhost:5173. Wrappers: `scripts/dev.ps1` (Windows) and `scripts/dev.sh`
(macOS/Linux).

Run every check:

```bash
uv run --project agent python scripts/check.py
```

Run the agent without touching the real mouse or keyboard (actions are logged instead):

```bash
cd agent && uv run python -m lapremote --input-dry-run
```

Print a recon report of this machine:

```bash
uv run --project agent python scripts/recon.py
```

Audit the built app with Lighthouse (agent running and serving the build):

```bash
cd web && npm run lighthouse -- http://127.0.0.1:7777/
```

Try the AI planner against your local model without running anything on the laptop:

```bash
uv run --project agent python scripts/ai_smoke.py demo
```

Measure preview bandwidth, latency and CPU, or click accuracy, against a throwaway agent (see the comments in `scripts/measure.py` and `web/tests/accuracy/tapAccuracy.ts`).

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Protocol](docs/PROTOCOL.md)
- [Platform matrix](docs/PLATFORM_MATRIX.md)
- [Testing](docs/TESTING.md)
- [AI assistant setup](docs/AI.md) (Ollama, optional Groq or Gemini)
- [HTTPS](docs/HTTPS.md) (mkcert or Tailscale, for voice input and the air mouse)
- [Security](docs/SECURITY.md)

## License

[MIT](LICENSE)

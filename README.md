# LapRemote

Turn your phone into a fast, good-looking control panel for your laptop: universal media control,
a gesture trackpad, live screen preview, context-aware controls and natural-language commands. It
runs entirely on your local Wi-Fi. No cloud, no accounts, 100% free and open source.

> **Status:** in active development, phase by phase. See [CHANGELOG.md](CHANGELOG.md) for what works today.

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

Print a recon report of this machine:

```bash
uv run --project agent python scripts/recon.py
```

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Protocol](docs/PROTOCOL.md)
- [Platform matrix](docs/PLATFORM_MATRIX.md)
- [Testing](docs/TESTING.md)

## License

[MIT](LICENSE)

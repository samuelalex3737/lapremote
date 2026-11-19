# Changelog

All notable changes to LapRemote. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Phase 0 - Recon and scaffold

- Agent package (`python -m lapremote`) on Python 3.12, managed by uv with a committed `uv.lock`.
- `config.py`: `~/.lapremote/config.json` with the spec defaults, validation, atomic saves, and a
  friendly error instead of overwriting a broken file.
- `system/platform_info.py`: OS, version, media CLI (`media-control` / `playerctl`) and Linux display
  server detection.
- `server.py`: FastAPI app factory with `GET /api/health`. Listens on 127.0.0.1 only until pairing
  lands in Phase 1.
- Remote web app scaffold: Vite 8, React 19, TypeScript 6 (strict), Tailwind CSS 4, zod. Health check
  screen with an offline state and retry.
- Tooling: ruff, mypy `--strict`, pytest, eslint (`strictTypeChecked`), tsc, vitest, Playwright
  (iPhone 15 + Pixel 8).
- Scripts: `dev.py` (agent with auto-reload + Vite with `/api` and `/ws` proxy), `check.py` (all
  checks with a summary), `recon.py` (host report).
- Docs: architecture (Mermaid), protocol (spec verbatim, clarifications, canonical message list,
  open questions), platform matrix, testing.

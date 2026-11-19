#!/usr/bin/env sh
# Run the agent (auto-reload) and the Vite dev server together.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
exec uv run --project "$root/agent" python "$root/scripts/dev.py"

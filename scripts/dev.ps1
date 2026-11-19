# Run the agent (auto-reload) and the Vite dev server together.
$root = Split-Path -Parent $PSScriptRoot
uv run --project "$root\agent" python "$root\scripts\dev.py"
exit $LASTEXITCODE

# The AI assistant

More > Ask LapRemote turns a sentence like "pause everything" or "open youtube and search lofi
beats" into a short list of the same actions the phone's buttons send. The model only proposes
data: the laptop checks every step against a fixed allowlist and the protocol's own validation
before anything runs. It can't run commands, open programs that aren't shortcuts, or visit sites
that aren't shortcuts.

## Setup (Ollama, the default, runs on the laptop)

1. Install [Ollama](https://ollama.com). On Windows: `winget install Ollama.Ollama`. It starts
   in the background and listens on `http://127.0.0.1:11434`.
2. Pick the model by memory: 16 GB of RAM or more, `qwen2.5:7b`; less than that,
   `qwen2.5:3b`. This command prints your memory and the recommendation:
   ```
   uv run --project agent python scripts/ai_smoke.py check
   ```
3. Download it, for example `ollama pull qwen2.5:7b` (about 4.7 GB).
4. If you picked a different model, set it in `~/.lapremote/config.json`:
   ```json
   "ai": { "provider": "ollama", "model": "qwen2.5:3b", "ollamaUrl": "http://127.0.0.1:11434" }
   ```
5. Restart LapRemote. The agent checks the model every 30 seconds. A phone sees the status when
   it connects, so reopen the app if you started Ollama after connecting.

Try the planner without running anything on the laptop:
```
uv run --project agent python scripts/ai_smoke.py demo
uv run --project agent python scripts/ai_smoke.py ask "turn it down a bit"
```

## Optional cloud providers (free tiers)

Set `"provider": "groq"` or `"provider": "gemini"` in `config.json`, and put the key in an
environment variable before starting LapRemote. Keys are never stored in `config.json`.

| Provider | Variable | Default model |
|---|---|---|
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Gemini | `GEMINI_API_KEY` | `gemini-2.0-flash` |

Set `"model"` to use another model. The Gemini key goes in a request header, not the URL.

With a cloud provider, each request sends the laptop summary below to that company.

## What the model sees

- The allowed actions and their fields, generated from `protocol.py`.
- A short summary: the media players (app, title, artist, status, position), the foreground
  app and its category and site, volume, brightness, the sleep timer, and shortcut and scene
  names and ids.
- Never window titles, typed text history, screenshots, tokens or file paths.

Requests and replies are never written to the log. The log keeps only the action types, how
many steps were dropped, and timings.

## Safety

- Only the owner can use it. Guests get "Only the owner can do that."
- Unknown action types and bad payloads are dropped and counted in the reply. The model gets
  one more try, told exactly what was wrong.
- Power actions, typing more than 200 characters, and launching an app shortcut always ask
  first. The confirmation is bound to the phone that asked and expires after 60 seconds.

## Speed

On a laptop without a big GPU the 7B model runs mostly on the CPU. Measured on this laptop
(16 GB, MX550): 8 to 22 seconds per request once loaded, and about a minute for the first
request after Ollama loads the model. `qwen2.5:3b`, or Groq, is much faster.

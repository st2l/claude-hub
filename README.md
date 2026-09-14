# claude-hub

Terminal UI for managing [Claude Code](https://claude.com/claude-code) model
providers: add gateways / direct API endpoints, store keys, fetch model lists,
assign models to Claude Code's 4 tiers (Fable / Opus / Sonnet / Haiku), and
switch between saved profiles — then launch `claude` with the chosen setup.

Pure Python 3 stdlib (curses), no dependencies.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/st2l/claude-hub/main/install.sh | bash
```

Requires: `python3`, `git`, and Claude Code (`npm install -g @anthropic-ai/claude-code`).

## Usage

```bash
claude-hub              # open TUI
claude-hub -L [args]    # launch claude with the configured providers/models
claude-hub -l           # list all models from all providers
claude-hub -r           # force-refresh model cache
```

### TUI

| Key | Action |
|-----|--------|
| `Tab` / `←` `→` | switch tabs: Dashboard · Providers · Models · Tiers · Profiles |
| `j`/`k` or `↑`/`↓` | navigate |
| `Enter` | select / edit / assign |
| `/` | search models |
| `a` / `e` / `d` | add / edit / delete (context-dependent) |
| `t` | toggle provider on/off |
| `L` | launch claude |
| `r` | refresh models from all providers |
| `q` | quit |

### What each tab does

- **Dashboard** — current profile, active provider, tier assignments, launch.
- **Providers** — add multiple backends. Two types:
  - `gateway` — CLIProxyAPI-style proxy exposing `/v1/models` (models get
    encoded to Claude-Code-compatible gateway IDs automatically);
  - `direct` — Anthropic-compatible API endpoint.
  Keys are stored in separate files (`chmod 600`), never in the config JSON.
- **Models** — everything from all active providers, searchable, one `Enter`
  away from being assigned to any tier.
- **Tiers** — map Claude Code's `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL`.
- **Profiles** — named tier presets; activate one and launch.

## Config

`~/.config/claude-hub/config.json`:

```json
{
  "providers": [
    {
      "name": "my gateway",
      "type": "gateway",
      "url": "https://gw.example.com",
      "key_file": "~/.secrets/my-key",
      "active": true
    }
  ],
  "tiers": {
    "FABLE": "claude-fable-5",
    "SONNET": "claude-sonnet-5",
    "OPUS": "claude-opus-4-8",
    "HAIKU": "claude-haiku-4-5-20251001"
  },
  "active_profile": "default",
  "profiles": { "default": { "...": "same shape as tiers" } }
}
```

Launch sets `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, the four
`ANTHROPIC_DEFAULT_*_MODEL` vars and `CLAUDE_CODE_SUBAGENT_MODEL=inherit`,
then execs `claude`. Aliases / other claude wrappers are never touched.

## How it launches claude

`claude-hub -L` is equivalent to:

```bash
ANTHROPIC_BASE_URL=<provider url> \
ANTHROPIC_AUTH_TOKEN=<key> \
CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1 \
ANTHROPIC_DEFAULT_FABLE_MODEL=... \
ANTHROPIC_DEFAULT_OPUS_MODEL=... \
ANTHROPIC_DEFAULT_SONNET_MODEL=... \
ANTHROPIC_DEFAULT_HAIKU_MODEL=... \
CLAUDE_CODE_SUBAGENT_MODEL=inherit \
claude
```

## License

MIT

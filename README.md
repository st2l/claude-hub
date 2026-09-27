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
claude-hub -u           # update claude-hub in place (-c check only)
claude-hub -s on|off    # statusline in Claude Code
```

There is no provider out of the box. Open the TUI, press `a` on the
**Providers** tab, point it at your own gateway or API endpoint.

### TUI

| Key | Action |
|-----|--------|
| `Tab` / `←` `→` | switch tabs: Dashboard · Providers · Models · Tiers · Profiles · Context |
| `j`/`k` or `↑`/`↓` | navigate |
| `Enter` | select / edit / assign |
| `/` | search models |
| `a` / `e` / `d` | add / edit / delete (context-dependent) |
| `t` | toggle provider on/off |
| `L` | launch claude |
| `r` | refresh models from all providers |
| `u` | update claude-hub |
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
- **Context**: context window, compaction and the statusline (see below).

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
  "profiles": { "default": { "...": "same shape as tiers" } },
  "context": {
    "window": 1000000,
    "disable_compact": true,
    "statusline": true
  }
}
```

Launch sets `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, the four
`ANTHROPIC_DEFAULT_*_MODEL` vars and `CLAUDE_CODE_SUBAGENT_MODEL=inherit`,
then execs `claude`. Aliases / other claude wrappers are never touched.

## Context window

Claude Code trusts a model's advertised context window only on the
first-party API. Behind a gateway it cannot vouch for the model, falls back to
a 200k floor and starts auto-compacting there, however much the model really
holds. The one lever is `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, and Claude Code
reads it only while `DISABLE_COMPACT` is set, so the two always travel
together.

claude-hub therefore launches with a 1M window and compaction off by default:

```bash
DISABLE_COMPACT=1 CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000
```

The price is real: no auto-compaction and no manual `/compact` either. Nothing
trims the conversation any more, and past the model's real window the API
simply starts rejecting requests, with `/clear` as the way out. That is what
the statusline is for. Change the window, or hand compaction back to Claude
Code, on the **Context** tab.

## Statusline

`claude_hub/statusline.py` is registered in `~/.claude/settings.json` at
install and on every launch, and prints two lines under the prompt:

```
Gemini 2.5 Pro · fable ↳hub │ ██████░░░░░░░░ 41% 428k/1.0M │ nocompact │ cache 87%
hub:google @gw.example.com │ myproject ⎇ main │ gemini-pro 428k · haiku-4-5 12k │ $1.84~
```

What it adds over the built-in display:

- gateway model ids (`claude-fable-5-dd-<reversed>`) are decoded back to the
  real model name, and the active tier and profile are shown;
- the bar is drawn against the model's **real** window from
  `~/.config/claude-hub/context-windows.json`, not against whatever
  `CLAUDE_CODE_MAX_CONTEXT_TOKENS` claims, and turns red before the real
  limit, which is the warning that makes compaction-off survivable;
- per-model token totals for the session, parsed incrementally from the
  transcript;
- cost, cache hit ratio and rate limits when Claude Code reports them.

It is pure stdlib, imports nothing from the package, and never raises: on any
failure it degrades to a single line. `claude-hub -s off` removes it, and an
existing statusline from another tool is never overwritten.

## Updating

```bash
claude-hub -u          # fetch and fast-forward this install
claude-hub -u -c       # only report whether an update is waiting
claude-hub -u -f       # discard local edits to the checkout and update
```

Or press `u` in the TUI. The update is a `git reset --hard` onto
`origin/main` inside the install directory, so local edits there are reported
and refused rather than merged.

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

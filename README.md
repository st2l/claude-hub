# claude-hub

Terminal UI for managing [Claude Code](https://claude.com/claude-code) model
providers: add gateways / direct API endpoints, store keys, fetch model lists,
assign models to Claude Code's 4 tiers (Fable / Opus / Sonnet / Haiku), and
switch between saved profiles — then launch `claude` with the chosen setup.

Pure Python 3 stdlib (curses), no dependencies on Linux and macOS. Runs on
Linux, macOS and Windows 10/11.

## Install

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/st2l/claude-hub/main/install.sh | bash
```

Requires `python3` and `git`.

### Windows

In PowerShell (no Administrator, no git needed):

```powershell
irm https://raw.githubusercontent.com/st2l/claude-hub/main/install.ps1 | iex
```

Requires Python 3.11+ with pip (`winget install Python.Python.3.13`). The
installer pip-installs claude-hub plus [windows-curses] (Windows has no stdlib
`curses`), then puts `claude-hub.exe` on your user PATH. Re-run it to upgrade.

Already have Python set up? `pip install --user windows-curses` plus
`pip install --user https://github.com/st2l/claude-hub/archive/refs/heads/main.zip`
does the same thing.

[windows-curses]: https://pypi.org/project/windows-curses/

### Claude Code itself

claude-hub launches `claude`, so Claude Code has to be installed:

```bash
curl -fsSL https://claude.ai/install.sh | bash   # Linux / macOS
```

```powershell
irm https://claude.ai/install.ps1 | iex          # Windows
```

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

- **Dashboard** — current profile, the provider a launch will route to, tier
  assignments, launch.
- **Providers** — add multiple backends. Two types:
  - `gateway` — CLIProxyAPI-style proxy exposing `/v1/models` (models get
    encoded to Claude-Code-compatible gateway IDs automatically);
  - `direct` — Anthropic-compatible API endpoint.
  Keys are stored in separate files (`chmod 600`), never in the config JSON.
  Gateways carry an `encode_model_ids` flag (set when adding/editing, shown as
  `raw` in the list when off). Leave it on for a gateway that decodes
  claude-hub's `claude-fable-5-dd-…` id disguise; turn it off for one that
  expects the raw `openrouter/…`-style id and otherwise answers
  `no active credentials for provider: claude-fable-5-dd-…`.
- **Models** — everything from all active providers, searchable, one `Enter`
  away from being assigned to any tier. Claude Code routes a whole session
  through one gateway, so at launch claude-hub sends it to whichever active
  provider actually serves the models the tiers point at — assign models from
  any provider and the right gateway is picked for you.
- **Tiers** — map Claude Code's `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL`.
- **Profiles** — named tier presets; activate one and launch.
- **Context**: context window, compaction and the statusline (see below).

## Config

`~/.config/claude-hub/config.json`, or `%APPDATA%\claude-hub\config.json` on
Windows:

```json
{
  "providers": [
    {
      "name": "my gateway",
      "type": "gateway",
      "url": "https://gw.example.com",
      "key_file": "~/.secrets/my-key",
      "active": true,
      "encode_model_ids": true
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
    "disable_compact": false,
    "statusline": true
  }
}
```

Provider keys live in their own files, never in that JSON: `chmod 600` on
POSIX, `icacls /inheritance:r /grant:r <you>:(R,W)` on Windows. If the lockdown
fails the TUI says so in the status line instead of claiming the key is saved
safely.

Launch sets `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, the four
`ANTHROPIC_DEFAULT_*_MODEL` vars and `CLAUDE_CODE_SUBAGENT_MODEL=inherit`,
then execs `claude`. Aliases / other claude wrappers are never touched.
`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` come from the active provider that
serves the assigned tier models; with a single active provider it is simply
that one.

## Context window

Claude Code finds a model's real window from the `claude-*` name inside its
id, gateway or not: `cc/claude-opus-5` resolves to 1M and
`no-think/cc/claude-haiku-4-5-20251001` to 200k, with no help from us. So
claude-hub launches with **compaction on** and overrides nothing, and tiers
holding models with different windows each compact against their own.

A model Claude Code cannot name is a different case. It assumes 200k and, as
of 2.1.x, auto-compaction holds the session there. claude-hub lifts that when
it knows better, using the window the provider advertises in `/v1/models`
(`context_length` / `max_input_tokens`), or an entry in
`context-windows.json`, which overrides it:

```bash
CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1
CLAUDE_CODE_AUTO_COMPACT_WINDOW=<the model's real window>
```

Compaction stays on; only the 200k assumption is lifted. With several unknown
models assigned, the trigger is the smallest of their windows, so the lowest
one stays safe.

Turning compaction off on the **Context** tab is the other regime, and it is a
real trade. `CLAUDE_CODE_MAX_CONTEXT_TOKENS` is read only while
`DISABLE_COMPACT` is set, so one window applies to every model and manual
`/compact` stops working too:

```bash
DISABLE_COMPACT=1 CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000
```

Nothing trims the conversation then, and past a model's real window the API
starts rejecting requests, with `/clear` as the way out. Worth it only to hold
a window Claude Code would not otherwise grant.

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
and refused rather than merged. The Windows install is a pip install with no
clone to reset, so `-u` there says so and prints the installer command instead.

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

## Windows notes

- **The TUI needs `windows-curses`.** Without it `claude-hub` prints the pip
  command to fix it; `-l`, `-L` and `-r` keep working either way.
- **Box-drawing characters** are swapped for ASCII when the console code page
  is not UTF-8 (`chcp` shows 866 or 1251), so nothing turns into mojibake.
  Windows Terminal with UTF-8 gets the full glyph set.
- **`claude-hub` not found after install?** Open a new terminal — PATH changes
  do not reach already-running shells.
- **The statusline** is registered with the interpreter claude-hub runs on
  (`sys.executable`), not `python3`, which Windows does not have. It always
  emits UTF-8 regardless of the console code page.
- **`claude-hub -u`** needs a git clone; the pip install does not have one. Re-run
  `install.ps1` to upgrade.
- **WSL** is the POSIX install: run `install.sh` inside WSL, not `install.ps1`.

## Development

```bash
python3 -m unittest discover -s tests -t .   # platform branches, both OSes
python3 -m claude_hub                        # run from a clone
```

## License

MIT

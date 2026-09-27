"""Entry point for claude-hub."""
import sys

from claude_hub import config
from claude_hub.tui import run_tui
from claude_hub.launcher import launch
from claude_hub import integration
from claude_hub import models as mdl
from claude_hub import updater


def main():
    cfg = config.load()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ("-h", "--help"):
            _usage()
            return
        if cmd in ("-l", "--list"):
            _list_models(cfg)
            return
        if cmd in ("-L", "--launch"):
            sys.argv.pop(1)
            launch(cfg, sys.argv[1:])
            return
        if cmd in ("-r", "--refresh"):
            models = mdl.all_models(cfg, force=True)
            print(f"Refreshed: {len(models)} models from "
                  f"{len(cfg.get('providers', []))} providers")
            return
        if cmd in ("-u", "--update"):
            updater.main(sys.argv[2:])
            return
        if cmd in ("-s", "--statusline"):
            _statusline(cfg, sys.argv[2:])
            return

    run_tui(cfg)


def _usage():
    print("""\033[1mclaude-hub\033[0m — TUI for managing Claude Code providers

\033[1mUsage:\033[0m
  claude-hub              Open TUI
  claude-hub -l           List all models
  claude-hub -L [args]    Launch claude with current config
  claude-hub -r           Refresh model cache
  claude-hub -u           Update claude-hub (-c check only, -f discard edits)
  claude-hub -s [on|off]  Statusline in Claude Code (no arg: show state)
  claude-hub -h           This help

\033[1mTUI Keys:\033[0m
  Tab/←→    Switch tabs (Dashboard, Providers, Models, Tiers, Profiles, Context)
  j/k/↑↓    Navigate
  Enter      Select / Edit
  /          Search (Models tab)
  L          Launch claude
  r          Refresh models
  u          Update claude-hub
  q          Quit""")


def _statusline(cfg, argv):
    want = argv[0].lower() if argv else ""
    if want in ("on", "off"):
        cfg["context"] = config.context_settings(cfg)
        cfg["context"]["statusline"] = want == "on"
        config.save(cfg)
        ok, why = (
            integration.install_statusline() if want == "on"
            else integration.remove_statusline()
        )
        print(f"statusline {want}: {why}" if ok else f"[x] {why}")
        return

    state = {
        "ours": "registered by claude-hub",
        "other": "another statusline is configured",
        "none": "not registered",
    }[integration.statusline_state()]
    print(f"{state}\ncommand: {integration.statusline_command()}")


def _list_models(cfg):
    models = mdl.all_models(cfg, force=True)
    if not models:
        print("No models. Check your providers and API keys.")
        return
    print(f"{'Provider':<16} {'Model':<42} {'ID'}")
    print("─" * 100)
    for m in models:
        display_id = m.get("clean_id", m["id"])
        print(f"{m['provider']:<16} {m['name']:<42} {display_id}")
    providers = set(m["provider"] for m in models)
    print(f"\n{len(models)} models from {len(providers)} providers")


if __name__ == "__main__":
    main()

"""Wiring claude-hub into Claude Code itself.

Two things live in Claude Code's own files rather than in ours:

  * the statusline, which Claude Code runs as an external command and which
    therefore has to be registered in ~/.claude/settings.json;
  * the real context window of each model, which Claude Code cannot know for
    a gateway model and which the statusline needs in order to draw an honest
    bar.

Everything here is idempotent, so launcher.py can call it on every launch.
"""
import json
import shutil
from pathlib import Path

from claude_hub.config import CONFIG_DIR, _ensure_dirs

CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"
STATUSLINE = Path(__file__).resolve().parent / "statusline.py"
CTX_WINDOWS_FILE = CONFIG_DIR / "context-windows.json"

# Real windows, matched as a substring of the decoded model id. These are the
# numbers the upstream API enforces, which is what decides when requests start
# getting rejected. Claude Code's own figure is not that number: it is a 200k
# floor for anything it does not recognise, or whatever we told it through
# CLAUDE_CODE_MAX_CONTEXT_TOKENS.
#
# The claude-* values are Claude Code's own `context.window` for each model.
# The Claude 5 generation and Opus 4.7 onwards are natively 1M; everything
# older is 200k, whatever tier it sits in.
DEFAULT_CTX_WINDOWS = {
    "_comment": (
        "Real context window per model, matched as a substring of the decoded "
        "model id. Used by claude-hub's statusline to draw the bar against the "
        "window the upstream API actually enforces. Add a model here whenever "
        "you assign a new one in claude-hub."
    ),
    "claude-fable-5": 1000000,
    "claude-mythos-5": 1000000,
    "claude-opus-5": 1000000,
    "claude-opus-4-8": 1000000,
    "claude-opus-4-7": 1000000,
    "claude-sonnet-5": 1000000,
    "claude-opus-4-6": 200000,
    "claude-opus-4-5": 200000,
    "claude-opus-4-1": 200000,
    "claude-sonnet-4": 200000,
    "claude-haiku-4-5": 200000,
    "claude-3-5-haiku": 200000,
    "gemini": 1048576,
    "gpt-4.1": 1048576,
    "glm": 200000,
    "qwen": 262144,
    "deepseek": 131072,
}


def statusline_command() -> str:
    """The command Claude Code should run, pointing at this very checkout."""
    return f"python3 {STATUSLINE}"


def _read_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_settings(data: dict):
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    # Claude Code's settings are the user's, not ours. Keep one backup of
    # whatever was there before we first touched it.
    backup = SETTINGS_FILE.with_suffix(".json.claude-hub-backup")
    if SETTINGS_FILE.exists() and not backup.exists():
        try:
            shutil.copy2(SETTINGS_FILE, backup)
        except OSError:
            pass
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def statusline_state() -> str:
    """One of: "ours", "other", "none"."""
    line = _read_settings().get("statusLine")
    if not isinstance(line, dict) or not line.get("command"):
        return "none"
    return "ours" if "statusline.py" in line["command"] else "other"


def install_statusline(force: bool = False) -> tuple[bool, str]:
    """Register our statusline. Leaves a foreign one alone unless forced."""
    if not STATUSLINE.exists():
        return False, f"missing {STATUSLINE}"

    state = statusline_state()
    if state == "other" and not force:
        return False, "another statusline is configured, not replacing it"

    settings = _read_settings()
    wanted = {
        "type": "command",
        "command": statusline_command(),
        "padding": 0,
    }
    if settings.get("statusLine") == wanted:
        return True, "already registered"
    settings["statusLine"] = wanted
    try:
        _write_settings(settings)
    except OSError as error:
        return False, str(error)
    return True, "registered in ~/.claude/settings.json"


def remove_statusline() -> tuple[bool, str]:
    if statusline_state() != "ours":
        return False, "not ours, leaving it alone"
    settings = _read_settings()
    settings.pop("statusLine", None)
    try:
        _write_settings(settings)
    except OSError as error:
        return False, str(error)
    return True, "removed from ~/.claude/settings.json"


def ensure_context_windows() -> Path:
    """Seed the per-model window file once, then never touch it again."""
    _ensure_dirs()
    if not CTX_WINDOWS_FILE.exists():
        try:
            CTX_WINDOWS_FILE.write_text(
                json.dumps(DEFAULT_CTX_WINDOWS, indent=2, ensure_ascii=False) + "\n"
            )
        except OSError:
            pass
    return CTX_WINDOWS_FILE


def context_windows() -> dict:
    try:
        data = json.loads(CTX_WINDOWS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def install(statusline: bool = True) -> list[str]:
    """Everything Claude Code needs from us. Safe to repeat."""
    notes = []
    ensure_context_windows()
    if statusline:
        ok, why = install_statusline()
        notes.append(f"statusline: {why}" if ok else f"statusline NOT set: {why}")
    return notes


def main():
    for note in install():
        print(note)
    print(f"context windows: {CTX_WINDOWS_FILE}")


if __name__ == "__main__":
    main()

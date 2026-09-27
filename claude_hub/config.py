"""Persistent configuration: providers, tiers, profiles."""
import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "claude-hub"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = CONFIG_DIR / "cache"

DEFAULT_TIERS = {
    "FABLE": "claude-fable-5",
    "SONNET": "claude-sonnet-5",
    "OPUS": "claude-opus-4-8",
    "HAIKU": "claude-haiku-4-5-20251001",
}

TIER_LABELS = {
    "FABLE": "Fable  — primary model",
    "SONNET": "Sonnet — working model",
    "OPUS": "Opus   — complex tasks",
    "HAIKU": "Haiku  — fast / background",
}

# Claude Code clamps every model it cannot vouch for to 200k tokens, and
# through a gateway it can never vouch for one. CLAUDE_CODE_MAX_CONTEXT_TOKENS
# lifts the clamp, but only while DISABLE_COMPACT is set, so the two always
# travel together. See claude_hub/launcher.py for what gets exported.
DEFAULT_CONTEXT = {
    "window": 1_000_000,
    "disable_compact": True,
    "statusline": True,
}


def _ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    _ensure_dirs()
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return _defaults()


def save(cfg: dict):
    _ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def _defaults() -> dict:
    """A fresh config. No provider is assumed: add yours on the Providers tab."""
    return {
        "providers": [],
        "tiers": dict(DEFAULT_TIERS),
        "active_profile": "default",
        "profiles": {
            "default": dict(DEFAULT_TIERS),
        },
        "context": dict(DEFAULT_CONTEXT),
    }


def context_settings(cfg: dict) -> dict:
    """Context settings with the defaults filled in.

    Merged rather than read straight out of the config so that a config file
    written by an older version still gets the 1M window.
    """
    merged = dict(DEFAULT_CONTEXT)
    stored = cfg.get("context")
    if isinstance(stored, dict):
        merged.update(stored)
    try:
        merged["window"] = max(1, int(merged["window"]))
    except (TypeError, ValueError):
        merged["window"] = DEFAULT_CONTEXT["window"]
    return merged


def get_key(provider: dict) -> str:
    kf = Path(provider.get("key_file", "")).expanduser()
    if kf.exists():
        return kf.read_text().strip()
    return provider.get("key", "")


def set_key(provider: dict, key: str):
    kf = Path(provider.get("key_file", "")).expanduser()
    if str(kf) == ".":
        kf = CONFIG_DIR / f"key-{provider['name'].lower().replace(' ', '-')}"
        provider["key_file"] = str(kf)
    kf.parent.mkdir(parents=True, exist_ok=True)
    kf.write_text(key)
    os.chmod(kf, 0o600)

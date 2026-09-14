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
    return {
        "providers": [
            {
                "name": "CPA st2l",
                "type": "gateway",
                "url": "https://ai.st2l.tech",
                "key_file": "~/.secrets/claude-key",
                "active": True,
            }
        ],
        "tiers": dict(DEFAULT_TIERS),
        "active_profile": "default",
        "profiles": {
            "default": dict(DEFAULT_TIERS),
        },
    }


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

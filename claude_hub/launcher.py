"""Launch claude with the configured environment."""
import os
import shutil
import subprocess
import sys

from claude_hub.config import get_key


def launch(cfg: dict, extra_args: list[str] | None = None):
    provider = None
    for p in cfg.get("providers", []):
        if p.get("active", True):
            provider = p
            break

    if not provider:
        print("\033[1;31mNo active provider configured.\033[0m")
        sys.exit(1)

    tiers = cfg.get("tiers", {})
    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = provider["url"]
    env["ANTHROPIC_AUTH_TOKEN"] = get_key(provider)
    env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] = "1"
    env["ANTHROPIC_DEFAULT_FABLE_MODEL"] = tiers.get(
        "FABLE", "claude-fable-5"
    )
    env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = tiers.get(
        "OPUS", "claude-opus-4-8"
    )
    env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = tiers.get(
        "SONNET", "claude-sonnet-5"
    )
    env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = tiers.get(
        "HAIKU", "claude-haiku-4-5-20251001"
    )
    env["CLAUDE_CODE_SUBAGENT_MODEL"] = "inherit"
    env.pop("ANTHROPIC_API_KEY", None)

    claude_bin = (
        shutil.which("claude") or
        os.path.expanduser("~/.local/bin/claude")
    )
    args = [claude_bin] + (extra_args or [])
    subprocess.run(args, env=env)

"""Launch claude with the configured environment."""
import os
import shutil
import subprocess
import sys

from claude_hub import integration
from claude_hub.config import context_settings, get_key


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

    _apply_context(env, cfg)

    claude_bin = (
        shutil.which("claude") or
        os.path.expanduser("~/.local/bin/claude")
    )
    args = [claude_bin] + (extra_args or [])
    subprocess.run(args, env=env)


def _apply_context(env: dict, cfg: dict):
    """Raise the context window and register the statusline.

    Claude Code trusts a model's advertised window only on the first-party
    API. Behind a gateway it falls back to a 200k floor and starts
    auto-compacting there, however much the model can really hold. The only
    lever is CLAUDE_CODE_MAX_CONTEXT_TOKENS, and it is read only while
    DISABLE_COMPACT is set, so setting the window also turns compaction off
    for good: no auto-compaction and no manual /compact either. Past the
    model's real window the API starts refusing requests and the way out is
    /clear.

    That is the trade this ships with, because being compacted at 200k on a
    model that holds far more is the worse half of it. The statusline draws
    against the real window from context-windows.json and turns red before the
    real limit, which is the warning the trade depends on. Turn it all off on
    the Context tab if you would rather have compaction back.
    """
    ctx = context_settings(cfg)

    if ctx.get("disable_compact", True):
        env["DISABLE_COMPACT"] = "1"
        env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(ctx["window"])
    else:
        # Let Claude Code decide, and do not leave a stale pair behind in the
        # environment we inherited.
        for name in ("DISABLE_COMPACT", "CLAUDE_CODE_MAX_CONTEXT_TOKENS"):
            env.pop(name, None)

    integration.install(statusline=ctx.get("statusline", True))

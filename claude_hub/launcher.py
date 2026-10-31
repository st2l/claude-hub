"""Launch claude with the configured environment."""
import os
import subprocess
import sys

from claude_hub import integration
from claude_hub import models as mdl
from claude_hub.config import context_settings, get_key
from claude_hub.system import IS_WINDOWS, find_claude


def resolve_provider(cfg: dict) -> tuple[dict | None, list[str]]:
    """Pick the active provider that actually serves the assigned tier models.

    Claude Code routes a whole session through a single ANTHROPIC_BASE_URL, so
    aggregating models from several gateways only works if we then send the
    session to the gateway that owns the models the tiers point at. We do that
    by matching each tier's model id against the model list every active
    provider advertises and choosing the one with the best coverage.

    Returns (provider, notes). `provider` is None only when nothing is active.
    `notes` carries human-readable warnings: tiers no provider could serve, or
    the fact that we fell back to the first active provider because no model
    list was reachable.
    """
    active = [p for p in cfg.get("providers", []) if p.get("active", True)]
    if not active:
        return None, []
    if len(active) == 1:
        return active[0], []

    tiers = cfg.get("tiers", {})
    tier_ids = {mdl._decode_cpa_id(mid) for mid in tiers.values() if mid}

    best, best_cover, best_served = active[0], -1, set()
    for p in active:
        served = set()
        for m in mdl.fetch_models(p):
            for key in (m.get("id"), m.get("clean_id")):
                if key:
                    served.add(mdl._decode_cpa_id(key))
        cover = len(tier_ids & served)
        if cover > best_cover:
            best, best_cover, best_served = p, cover, served

    if best_cover <= 0:
        # No active provider listed any of the assigned models: likely offline
        # with a cold cache. Keep the old behaviour — route to the first active
        # provider — but say so rather than failing silently.
        return active[0], [
            "could not match any tier model to a provider; routing to "
            f"{active[0]['name']}"
        ]

    missing = sorted(
        tier for tier, mid in tiers.items()
        if mid and mdl._decode_cpa_id(mid) not in best_served
    )
    notes = []
    if missing:
        notes.append(
            f"{best['name']} does not serve: {', '.join(missing)} "
            "— those requests may fail"
        )
    return best, notes


def tier_model_id(model_id: str, provider: dict) -> str:
    """Re-key a stored tier id to the scheme `provider` actually accepts.

    Tiers and profiles persist whatever id was current when they were saved,
    and launch() exports those strings verbatim. So a tier saved while a
    gateway wanted the "claude-fable-5-dd-…" disguise keeps sending it after
    the provider is switched to raw ids, and the gateway reads the disguise as
    a provider name: "401 No active credentials for provider:
    claude-fable-5-dd-eerf-tseb". Normalising here, at the one place an id
    leaves claude-hub, keeps the stored config valid under either scheme.
    """
    if not model_id:
        return model_id
    clean = mdl._decode_cpa_id(model_id)
    if provider.get("type") != "gateway":
        return clean
    if provider.get("encode_model_ids", True):
        return mdl._encode_cpa_id(clean)
    return clean


def launch(cfg: dict, extra_args: list[str] | None = None):
    provider, notes = resolve_provider(cfg)

    if not provider:
        print("\033[1;31mNo active provider configured.\033[0m")
        sys.exit(1)

    for note in notes:
        print(f"\033[1;33mclaude-hub: {note}\033[0m")

    tiers = {
        tier: tier_model_id(mid, provider)
        for tier, mid in cfg.get("tiers", {}).items()
    }
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

    for note in _apply_context(env, cfg, tiers, provider):
        print(f"\033[1;36mclaude-hub: {note}\033[0m")

    claude_bin = find_claude()
    if not claude_bin:
        print("\033[1;31mclaude not found on PATH.\033[0m")
        if IS_WINDOWS:
            print("Install it with:  irm https://claude.ai/install.ps1 | iex")
        else:
            print("Install it with:  curl -fsSL https://claude.ai/install.sh | bash")
        sys.exit(1)

    args = [claude_bin] + (extra_args or [])
    done = subprocess.run(args, env=env, check=False)
    sys.exit(done.returncode)


CLAUDE_CODE_FLOOR = 200_000

# Every window lever Claude Code reads, so a stale one never survives a
# relaunch under a different setting.
_WINDOW_VARS = (
    "DISABLE_COMPACT",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
    "CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT",
)


def _recognised(clean_id: str) -> bool:
    """Whether Claude Code can name this model, and so knows its real window.

    Its catalog is keyed on the claude-* name, which it finds inside a gateway
    id: "cc/claude-opus-5" resolves to the real 1M window and
    "no-think/cc/claude-haiku-4-5-20251001" to 200k, with no help from us.
    Anything without a claude-* name is the unknown-model case below.
    """
    return "claude-" in (clean_id or "").lower()


def _advertised(provider: dict) -> dict:
    """{clean id: window} for whatever the provider advertises a window for."""
    out = {}
    for m in mdl.fetch_models(provider):
        window = m.get("window")
        key = m.get("clean_id") or m.get("id")
        if key and window:
            try:
                out[key] = int(window)
            except (TypeError, ValueError):
                pass
    return out


def _real_window(clean_id: str, windows: dict, advertised: dict) -> int | None:
    """The upstream window for `clean_id`, provider first.

    The provider's own /v1/models figure is preferred because it is per model
    and needs no upkeep; context-windows.json is the manual override and the
    answer for a provider that advertises nothing.
    """
    lowered = (clean_id or "").lower()
    for key, value in windows.items():
        if key.startswith("_"):
            continue
        if key.lower() in lowered:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return advertised.get(clean_id)


def _apply_context(env: dict, cfg: dict, tiers: dict,
                   provider: dict | None = None) -> list[str]:
    """Set up compaction and the context window, and register the statusline.

    Two regimes, because Claude Code ties the window to compaction:

    Compaction on (the default). Claude Code works out each model's real
    window from its name, so the tiers can hold models with different windows
    and each is compacted against its own -- which is the point of leaving
    this on. Nothing is overridden for a recognised model. An unrecognised one
    is assumed to be 200k and, as of 2.1.x, held there by auto-compaction; for
    those we lift the enforcement and set the compaction trigger from
    context-windows.json so a 1M non-Claude model is not strangled at 200k.

    Compaction off. CLAUDE_CODE_MAX_CONTEXT_TOKENS is read only while
    DISABLE_COMPACT is set, so one global window applies to every model and
    /compact stops working too. Past a model's real limit the API starts
    refusing requests and the way out is /clear. Worth it only to hold a
    window Claude Code would not otherwise grant.

    Returns notes for the launcher to print.
    """
    ctx = context_settings(cfg)
    for name in _WINDOW_VARS:
        env.pop(name, None)

    if ctx.get("disable_compact", False):
        env["DISABLE_COMPACT"] = "1"
        env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(ctx["window"])
        integration.install(statusline=ctx.get("statusline", True))
        return [
            f"compaction off; {ctx['window']:,} token window forced for every "
            "model (/compact disabled, use /clear)"
        ]

    windows = integration.context_windows()
    advertised = _advertised(provider) if provider else {}
    unknown = {}
    for mid in tiers.values():
        if not mid:
            continue
        clean = mdl._decode_cpa_id(mid)
        if _recognised(clean):
            continue
        real = _real_window(clean, windows, advertised)
        if real and real > CLAUDE_CODE_FLOOR:
            unknown[clean] = real

    notes = []
    if unknown:
        # Compaction stays on; this only stops Claude Code from pinning an
        # unrecognised model to the 200k it assumes. The trigger is the
        # smallest real window among them, so the lowest model stays safe.
        trigger = min(unknown.values())
        env["CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT"] = "1"
        env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(trigger)
        listed = ", ".join(sorted(unknown))
        notes.append(
            f"compaction on; {listed} unknown to Claude Code, compacting at "
            f"{trigger:,} (its real window) instead of the 200k it assumes"
        )
    else:
        notes.append(
            "compaction on; Claude Code uses each model's own window"
        )

    integration.install(statusline=ctx.get("statusline", True))
    return notes

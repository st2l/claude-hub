#!/usr/bin/env python3
"""Claude Code statusline, claude-hub aware.

Reads the status payload on stdin, prints two lines.

claude-hub specifics handled here:
  * gateway model ids (``claude-fable-5-dd-<reversed>``) are decoded back to
    the real model name before display;
  * the active tier and profile are resolved from the env vars claude-hub
    exports at launch, falling back to its config file;
  * the context window size is overridable per model, because Claude Code
    cannot know the window of a model it does not recognise.

Claude Code runs this as a plain script, outside claude-hub's process and
without PYTHONPATH, so it imports nothing from the package and stays pure
stdlib. It never raises: any failure degrades to a minimal line.

Registered in ~/.claude/settings.json by claude_hub/integration.py, or by hand:

    "statusLine": {"type": "command", "command": "python3 <path to this file>"}
"""
import json
import os
import sys
import time
from pathlib import Path

HOME = Path.home()
HUB_CONFIG = HOME / ".config" / "claude-hub" / "config.json"
HUB_CACHE = HOME / ".config" / "claude-hub" / "cache"
CTX_OVERRIDES = HOME / ".config" / "claude-hub" / "context-windows.json"
STATE_DIR = HOME / ".cache" / "claude-statusline"

TIERS = ("FABLE", "OPUS", "SONNET", "HAIKU")


# --------------------------------------------------------------------------
# rendering helpers

def paint(text, code):
    if not code:
        return str(text)
    return "\x1b[%sm%s\x1b[0m" % (code, text)


DIM = "2"
BOLD = "1"
CYAN = "36"
BLUE = "34"
GREEN = "32"
YELLOW = "33"
RED = "31"
MAGENTA = "35"
SEP = paint(" │ ", DIM)


def human(n):
    n = int(n or 0)
    if n < 1000:
        return str(n)
    if n < 100_000:
        return "%.1fk" % (n / 1000.0)
    if n < 1_000_000:
        return "%dk" % round(n / 1000.0)
    return "%.1fM" % (n / 1_000_000.0)


def bar(fraction, width=14):
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    if fraction >= 0.90:
        colour = RED
    elif fraction >= 0.75:
        colour = YELLOW
    else:
        colour = GREEN
    return paint("█" * filled, colour) + paint("░" * (width - filled), DIM)


# --------------------------------------------------------------------------
# claude-hub

def decode_hub_id(model_id):
    """Undo claude-hub's gateway id encoding."""
    if not model_id or "-dd-" not in model_id:
        return model_id
    tail = model_id.split("-dd-", 1)[1]
    segments = tail.split("/")
    return "/".join(s[::-1] for s in reversed(segments))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default if default is not None else {}


def hub_tiers():
    """Tier -> model id, from the env claude-hub exported, else its config."""
    from_env = {}
    for tier in TIERS:
        value = os.environ.get("ANTHROPIC_DEFAULT_%s_MODEL" % tier)
        if value:
            from_env[tier] = value
    if from_env:
        return from_env
    return read_json(HUB_CONFIG).get("tiers", {})


def hub_profile():
    return read_json(HUB_CONFIG).get("active_profile")


def hub_model_name(clean_id):
    """Pretty name for a model, from claude-hub's cached provider listing."""
    if not HUB_CACHE.is_dir():
        return None
    for cache_file in HUB_CACHE.glob("models-*.json"):
        for entry in read_json(cache_file).get("models", []):
            if entry.get("clean_id") == clean_id or entry.get("id") == clean_id:
                return entry.get("name") or None
    return None


def gateway_host():
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    if not base:
        return None
    host = base.split("//", 1)[-1].split("/", 1)[0]
    return host or None


DEFAULT_WINDOWS = {
    "gemini": 1_000_000,
    "gpt-4.1": 1_000_000,
    "glm": 200_000,
    "qwen": 262_144,
    "deepseek": 131_072,
}

CLAUDE_CODE_FLOOR = 200_000


def compaction_off():
    value = os.environ.get("DISABLE_COMPACT", "").strip().lower()
    return value not in ("", "0", "false", "no")


def context_window(payload, clean_id):
    """(real window of the model, what Claude Code believes it is).

    These diverge for two different reasons and both matter.

    Claude Code clamps any model it cannot vouch for to 200k and only lifts
    that on the first-party API, so through a gateway its number is a floor
    rather than the truth. And when CLAUDE_CODE_MAX_CONTEXT_TOKENS is in play
    its number is whatever we told it, which is not evidence of anything.

    The real window is what decides when the API starts rejecting requests,
    so the bar is drawn against that one.
    """
    claimed = int((payload.get("context_window") or {}).get(
        "context_window_size") or CLAUDE_CODE_FLOOR)
    lowered = (clean_id or "").lower()

    for key, value in read_json(CTX_OVERRIDES).items():
        if key.startswith("_"):
            continue
        if key.lower() in lowered:
            return int(value), claimed

    if clean_id and not clean_id.startswith("claude-"):
        for key, value in DEFAULT_WINDOWS.items():
            if key in lowered:
                return value, claimed

    # Nothing known. Claude Code's own number is only trustworthy while it is
    # the one doing the deciding.
    return (CLAUDE_CODE_FLOOR if compaction_off() else claimed), claimed


# --------------------------------------------------------------------------
# per-model token totals, parsed incrementally from the transcript

def model_breakdown(transcript_path, session_id):
    """{model: total tokens} for the whole session.

    The transcript is append-only, so only the bytes added since the last
    render are parsed. Everything before that comes from a state file.
    """
    if not transcript_path:
        return {}
    source = Path(transcript_path)
    try:
        size = source.stat().st_size
    except OSError:
        return {}

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / ("%s.json" % (session_id or source.stem))
    state = read_json(state_file, {"offset": 0, "totals": {}})
    offset = int(state.get("offset", 0))
    totals = dict(state.get("totals", {}))
    if offset > size:  # transcript was rewritten, start over
        offset, totals = 0, {}

    try:
        with source.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
            offset = handle.tell()
    except OSError:
        return totals

    # A trailing partial line is left for the next run.
    text = chunk.decode("utf-8", "replace")
    if text and not text.endswith("\n"):
        cut = text.rfind("\n")
        if cut == -1:
            return totals
        offset -= len(text[cut + 1:].encode("utf-8"))
        text = text[:cut + 1]

    for line in text.splitlines():
        if '"usage"' not in line:
            continue
        try:
            message = (json.loads(line).get("message") or {})
        except Exception:
            continue
        usage = message.get("usage")
        model = message.get("model")
        if not usage or not model:
            continue
        spent = (usage.get("input_tokens", 0)
                 + usage.get("cache_creation_input_tokens", 0)
                 + usage.get("output_tokens", 0))
        totals[model] = totals.get(model, 0) + spent

    try:
        state_file.write_text(json.dumps({"offset": offset, "totals": totals}))
    except OSError:
        pass
    return totals


# --------------------------------------------------------------------------

def git_branch(cwd):
    """Read .git/HEAD directly. Cheaper than spawning git on every render."""
    directory = Path(cwd or ".").resolve()
    for candidate in [directory] + list(directory.parents):
        head = candidate / ".git" / "HEAD"
        if head.is_file():
            try:
                content = head.read_text().strip()
            except OSError:
                return None
            if content.startswith("ref: refs/heads/"):
                return content.split("refs/heads/", 1)[1]
            return content[:7]
    return None


def build(payload):
    model = payload.get("model") or {}
    raw_id = model.get("id", "")
    clean_id = decode_hub_id(raw_id)
    encoded = clean_id != raw_id

    if encoded:
        # Claude Code's display_name is meaningless for a gateway id.
        label = hub_model_name(clean_id) or clean_id.split("/")[-1]
    else:
        label = model.get("display_name") or hub_model_name(clean_id) or clean_id
    label = label or "?"

    # Only name the tier when it is unambiguous: claude-hub happily maps
    # several tiers to one model, and then the id cannot tell them apart.
    tiers = hub_tiers()
    matching = [t.lower() for t in TIERS if tiers.get(t) == raw_id]
    tier = matching[0] if len(matching) == 1 else None

    window, claimed = context_window(payload, clean_id)
    no_compact = compaction_off()
    context = payload.get("context_window") or {}
    used = int(context.get("total_input_tokens") or 0)
    fraction = (used / window) if window else 0.0
    percent = int(round(fraction * 100))

    # ---- line one -------------------------------------------------------
    first = [paint(label, BOLD + ";" + CYAN)]
    if tier:
        first[-1] += paint(" · " + tier, DIM)
    if encoded:
        first[-1] += paint(" ↳hub", MAGENTA)

    first.append("%s %s %s" % (
        bar(fraction),
        paint("%d%%" % percent, YELLOW if percent >= 75 else ""),
        paint("%s/%s" % (human(used), human(window)), DIM)))

    if no_compact:
        # Nothing will trim the conversation now, not even /compact. Once the
        # bar fills, the API starts refusing requests, so this has to shout.
        if fraction >= 0.90:
            first.append(paint(" ПРЕДЕЛ МОДЕЛИ, /clear ", BOLD + ";37;41"))
        elif fraction >= 0.75:
            first.append(paint("nocompact, скоро предел", YELLOW))
        else:
            first.append(paint("nocompact", DIM))
    elif claimed < window:
        # The model holds more than Claude Code is willing to believe, so it
        # will compact early. Say where that lands, the bar alone would lie.
        first.append(paint("compact@" + human(claimed), YELLOW))

    out_tokens = int(context.get("total_output_tokens") or 0)
    if out_tokens:
        first.append(paint("out ", DIM) + human(out_tokens))

    cache = payload.get("prompt_cache") or {}
    if cache.get("hit_ratio") is not None:
        ratio = int(round(cache["hit_ratio"] * 100))
        first.append(paint("cache ", DIM) + paint("%d%%" % ratio,
                                                  GREEN if ratio >= 70 else YELLOW))

    # ---- line two -------------------------------------------------------
    second = []
    profile = hub_profile()
    host = gateway_host()
    if host:
        tag = "hub:%s" % profile if profile else "hub"
        second.append(paint(tag, BLUE) + paint(" @" + host, DIM))

    workspace = payload.get("workspace") or {}
    cwd = workspace.get("current_dir") or payload.get("cwd") or ""
    if cwd:
        name = Path(cwd).name or cwd
        branch = git_branch(cwd)
        second.append(paint(name, GREEN) + (paint(" ⎇ " + branch, DIM) if branch else ""))

    totals = model_breakdown(payload.get("transcript_path"),
                             payload.get("session_id"))
    if len(totals) > 1:
        ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:3]
        parts = ["%s %s" % (decode_hub_id(m).split("/")[-1].replace("claude-", ""),
                            human(v)) for m, v in ranked]
        second.append(paint(" · ".join(parts), DIM))

    effort = (payload.get("effort") or {}).get("level")
    if effort:
        second.append(paint("effort ", DIM) + effort)
    if payload.get("fast_mode"):
        second.append(paint("fast", YELLOW))
    if (payload.get("thinking") or {}).get("enabled") is False:
        second.append(paint("no-think", DIM))

    limits = payload.get("rate_limits") or {}
    for key, short in (("five_hour", "5h"), ("seven_day", "7d")):
        entry = limits.get(key)
        if entry:
            value = int(round(entry.get("used_percentage", 0)))
            second.append(paint("%s %d%%" % (short, value),
                                RED if value >= 80 else DIM))

    cost = (payload.get("cost") or {}).get("total_cost_usd") or 0
    if cost > 0.0001:
        # Through a third-party gateway Claude Code prices against Anthropic's
        # own table, so this is indicative at best.
        suffix = "~" if host else ""
        second.append(paint("$%.2f%s" % (cost, suffix), DIM))

    lines = [SEP.join(first)]
    if second:
        lines.append(SEP.join(second))
    return "\n".join(lines)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(paint("statusline: no payload", DIM))
        return
    try:
        print(build(payload))
    except Exception as error:
        model = (payload.get("model") or {}).get("display_name", "?")
        print("%s %s" % (model, paint("(statusline: %s)" % error, RED)))


if __name__ == "__main__":
    main()

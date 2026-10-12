"""Model fetching, caching, and provider decoding."""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from claude_hub.config import CACHE_DIR, get_key


def _cache_path(provider: dict) -> Path:
    slug = provider["name"].lower().replace(" ", "-")
    return CACHE_DIR / f"models-{slug}.json"


def _encode_cpa_id(clean_id: str) -> str:
    if clean_id.startswith("claude-"):
        return clean_id
    segments = clean_id.split("/")
    rev = [s[::-1] for s in reversed(segments)]
    return "claude-fable-5-dd-" + "/".join(rev)


def _decode_cpa_id(cpa_id: str) -> str:
    if "-dd-" not in cpa_id:
        return cpa_id
    tail = cpa_id.split("-dd-", 1)[1]
    segments = tail.split("/")
    rev = [s[::-1] for s in reversed(segments)]
    return "/".join(rev)


def fetch_models(provider: dict, force: bool = False) -> list[dict]:
    cache = _cache_path(provider)
    if not force and cache.exists():
        try:
            data = json.loads(cache.read_text())
            age = time.time() - data.get("ts", 0)
            if age < 300:
                return data.get("models", [])
        except (json.JSONDecodeError, OSError):
            pass

    if provider["type"] == "gateway":
        models = _fetch_gateway(provider)
    else:
        models = _fetch_direct(provider)

    if models:
        cache.write_text(json.dumps({"ts": time.time(), "models": models}))
        return models

    if cache.exists():
        try:
            return json.loads(cache.read_text()).get("models", [])
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _get_json(url: str, headers: dict) -> dict | None:
    """GET `url` and parse the JSON body, or None if the call did not work.

    Callers fall back to a cached model list, so a failure is a signal here,
    not an error to raise.
    """
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _fetch_gateway(provider: dict) -> list[dict]:
    key = get_key(provider)
    url = provider["url"].rstrip("/") + "/v1/models"
    data = _get_json(url, {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    if data:
        raw = data.get("data", data.get("models", []))
        if raw:
            return [_parse_api_model(m) for m in raw]

    cpa_cache = Path.home() / ".claude" / "cache" / "gateway-models.json"
    if cpa_cache.exists():
        try:
            data = json.loads(cpa_cache.read_text())
            raw = data.get("models", [])
            return [_parse_cpa_cache_model(m) for m in raw]
        except (json.JSONDecodeError, OSError):
            pass

    return []


def _fetch_direct(provider: dict) -> list[dict]:
    key = get_key(provider)
    url = provider["url"].rstrip("/") + "/v1/models"
    data = _get_json(url, {
        "x-api-key": key,
        "Authorization": f"Bearer {key}",
        "anthropic-version": "2023-06-01",
    })
    if not data:
        return []
    raw = data.get("data", data.get("models", []))
    return [_parse_api_model(m) for m in raw]


def _parse_api_model(m: dict) -> dict:
    clean_id = m.get("id", "")
    provider = m.get("owned_by", "")
    name = m.get("display_name", "")

    if not provider:
        if "/" in clean_id:
            provider = clean_id.split("/")[0]
        elif clean_id.startswith("claude-"):
            provider = "anthropic"
        else:
            provider = "unknown"

    if not name:
        if "/" in clean_id:
            name = clean_id.split("/", 1)[-1]
        else:
            name = clean_id

    cpa_id = _encode_cpa_id(clean_id)

    return {
        "id": cpa_id,
        "clean_id": clean_id,
        "name": name,
        "provider": provider,
    }


def _parse_cpa_cache_model(m: dict) -> dict:
    cpa_id = m.get("id", "")
    name = m.get("display_name", cpa_id)
    clean_id = _decode_cpa_id(cpa_id)
    provider = "anthropic"

    if "-dd-" in cpa_id:
        obf = cpa_id.split("-dd-")[-1]
        if "/" in obf:
            provider = obf.split("/")[-1][::-1]
        else:
            provider = "unknown"

    return {
        "id": cpa_id,
        "clean_id": clean_id,
        "name": name,
        "provider": provider,
    }


def all_models(cfg: dict, force: bool = False) -> list[dict]:
    result = []
    seen = set()
    for prov in cfg.get("providers", []):
        if not prov.get("active", True):
            continue
        for m in fetch_models(prov, force=force):
            key = m.get("clean_id", m["id"])
            if key not in seen:
                seen.add(key)
                result.append(m)
    result.sort(key=lambda x: (x["provider"], x["name"]))
    return result

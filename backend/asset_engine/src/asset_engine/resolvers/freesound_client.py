"""Optional Freesound fallback client (best-effort, non-fatal)."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class FreesoundHit:
    source_url: str
    preview_url: str
    license: str
    username: str
    name: str


def is_enabled() -> bool:
    return bool(os.environ.get("FREESOUND_API_KEY"))


def search_top_hit(
    query: str,
    *,
    licenses: tuple[str, ...] = ("Creative Commons 0", "Attribution"),
    max_duration: float | None = None,
) -> FreesoundHit | None:
    api_key = os.environ.get("FREESOUND_API_KEY")
    if not api_key:
        return None

    filt = [f'license:"{licenses[0]}" OR license:"{licenses[1]}"']
    if max_duration is not None:
        filt.append(f"duration:[0 TO {max_duration}]")
    filter_expr = " ".join(filt)

    url = (
        "https://freesound.org/apiv2/search/text/?"
        f"query={quote_plus(query)}&token={quote_plus(api_key)}"
        "&fields=id,name,username,license,previews,url"
        f"&filter={quote_plus(filter_expr)}&page_size=1"
    )

    req = Request(url, headers={"User-Agent": "AS-asset-engine/1.0"})
    try:
        with urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None

    top = results[0]
    previews = top.get("previews") or {}
    preview_url = str(previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or "").strip()
    source_url = str(top.get("url") or "").strip()
    if not preview_url or not source_url:
        return None

    return FreesoundHit(
        source_url=source_url,
        preview_url=preview_url,
        license=str(top.get("license", "")),
        username=str(top.get("username", "")),
        name=str(top.get("name", "")),
    )


def cache_hit(hit: FreesoundHit, cache_file: Path) -> Path | None:
    req = Request(hit.preview_url, headers={"User-Agent": "AS-asset-engine/1.0"})
    try:
        with urlopen(req, timeout=12) as resp:
            blob = resp.read()
    except Exception:
        return None

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(blob)
    return cache_file

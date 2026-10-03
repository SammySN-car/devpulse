# src/devpulse/collectors/hackernews.py
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from ..models import Item, utcnow_iso

ALGOLIA = "https://hn.algolia.com/api/v1/search"


def _get(params: dict, transport: httpx.BaseTransport | None) -> dict | None:
    try:
        with httpx.Client(transport=transport, timeout=20.0,
                          headers={"User-Agent": "devpulse/0.1"}) as client:
            resp = client.get(ALGOLIA, params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError):
        return None


def _to_items(data: dict | None) -> list[Item]:
    if not isinstance(data, dict):
        return []
    out = []
    for hit in data.get("hits", []):
        link = hit.get("url") or \
            f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        netloc = urlparse(link).netloc or "(no link)"
        out.append(Item(
            url=link,
            title=hit.get("title") or "",
            source="hackernews",
            engagement=int(hit.get("points") or 0),
            context=f"link domain: {netloc}",
            fetched_at=utcnow_iso(),
        ))
    return out


def collect_show_hn(limit: int = 8, transport: httpx.BaseTransport | None = None) -> list[Item]:
    return _to_items(_get({"tags": "show_hn", "hitsPerPage": limit}, transport))[:limit]


def collect_top(limit: int = 8, transport: httpx.BaseTransport | None = None) -> list[Item]:
    return _to_items(_get({"tags": "front_page", "hitsPerPage": limit}, transport))[:limit]

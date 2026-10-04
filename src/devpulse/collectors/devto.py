# src/devpulse/collectors/devto.py
from __future__ import annotations

import httpx

from ..models import Item, utcnow_iso

API = "https://dev.to/api/articles"


def collect_articles(limit: int = 8, transport: httpx.BaseTransport | None = None) -> list[Item]:
    try:
        with httpx.Client(transport=transport, timeout=20.0,
                          headers={"User-Agent": "devpulse/0.1"}) as client:
            resp = client.get(API, params={"per_page": limit, "top": 1})
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for art in data[:limit]:
        desc = art.get("description") or "(no description)"
        out.append(Item(
            url=art.get("url", ""),
            title=art.get("title", ""),
            source="devto",
            engagement=int(art.get("public_reactions_count") or 0),
            context=f"published {art.get('published_at', '')} | {desc[:200]}",
            fetched_at=utcnow_iso(),
        ))
    return out

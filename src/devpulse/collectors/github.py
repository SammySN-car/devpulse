# src/devpulse/collectors/github.py
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import httpx

from ..models import Item, utcnow_iso

API = "https://api.github.com"


def _get(url: str, params: dict | None, token: str | None,
         transport: httpx.BaseTransport | None) -> dict | list | None:
    headers = {"User-Agent": "devpulse/0.1", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(transport=transport, timeout=20.0, headers=headers) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError):
        return None


def collect_rising(min_stars: int = 20, since_days: int = 7, token: str | None = None,
                   transport: httpx.BaseTransport | None = None,
                   today: date | None = None) -> list[Item]:
    since = (today or date.today()) - timedelta(days=since_days)
    data = _get(
        f"{API}/search/repositories",
        {"q": f"created:>{since.isoformat()} stars:>{min_stars}",
         "sort": "stars", "order": "desc", "per_page": 7},
        token, transport,
    )
    if not isinstance(data, dict):
        return []
    out = []
    for repo in data.get("items", []):
        desc = repo.get("description") or "(no description provided)"
        lang = repo.get("language") or "unknown"
        out.append(Item(
            url=repo.get("html_url", ""),
            title=repo.get("full_name", ""),
            source="github_rising",
            engagement=int(repo.get("stargazers_count") or 0),
            context=f"description: {desc[:200]} | language: {lang}",
            fetched_at=utcnow_iso(),
        ))
    return out


def collect_releases(watchlist: Sequence[str], token: str | None = None,
                     transport: httpx.BaseTransport | None = None,
                     now: datetime | None = None,
                     since_hours: int = 72, per_repo_cap: int = 2) -> list[Item]:
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(hours=since_hours)
    out: list[Item] = []
    for repo in watchlist:
        data = _get(f"{API}/repos/{repo}/releases", {"per_page": 5}, token, transport)
        if not isinstance(data, list):
            continue
        taken = 0
        for rel in data:
            if taken >= per_repo_cap:
                break
            try:
                created = datetime.fromisoformat(
                    str(rel.get("created_at", "")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if created < cutoff:
                continue
            out.append(Item(
                url=rel.get("html_url", ""),
                title=f"{repo} {rel.get('tag_name', '')}".strip(),
                source="github_release",
                engagement=1,
                context=f"release body: {(rel.get('body') or '(no notes)')[:200]}",
                fetched_at=utcnow_iso(),
            ))
            taken += 1
    return out

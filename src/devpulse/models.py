# src/devpulse/models.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class Item:
    url: str
    title: str
    source: str
    engagement: int
    context: str
    fetched_at: str
    engagement_pct: float = 0.0


@dataclass
class Judgment:
    url_hash: str
    relevance: int
    quality: int
    verdict: str
    model: str
    prompt_version: str
    status: str = "ok"
    judged_at: str = ""


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")

# src/devpulse/scoring.py
from __future__ import annotations

SLEEPER_MIN_QUALITY = 7
SLEEPER_MAX_ENGAGEMENT_PCT = 0.40


def sleeper_score(quality: int, engagement_pct: float) -> float:
    return quality * (1.0 - engagement_pct)


def is_sleeper_eligible(quality: int, engagement_pct: float) -> bool:
    return quality >= SLEEPER_MIN_QUALITY and engagement_pct <= SLEEPER_MAX_ENGAGEMENT_PCT

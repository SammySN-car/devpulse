# src/devpulse/composer.py
from __future__ import annotations

from .models import Item, Judgment
from .pipeline import DigestStats
from .scoring import is_sleeper_eligible

DISCORD_LIMIT = 2000
MAX_MESSAGE = 1900  # headroom below the Discord limit

_SOURCE_LABELS = {
    "github_rising": "github",
    "github_release": "github",
    "devto": "dev.to",
    "hackernews": "hackernews",
}


def _label(item: Item) -> str:
    return _SOURCE_LABELS.get(item.source, item.source)


def compose_digest(date_str: str, top: list[tuple[Item, Judgment]],
                   sleeper: tuple[Item, Judgment] | None, releases: list[Item],
                   stats: DigestStats, model: str) -> str:
    footer = (f"{stats.scanned} scanned, {stats.judged} judged,"
              f" {stats.minutes:.1f} min, {model}, on-device")

    if stats.skipped_reason and stats.skipped_reason != "no new items":
        return f"daily run skipped: {stats.skipped_reason}\n\n{footer}"
    if not top and not sleeper and stats.judged == 0:
        return f"no new items worth your time today\n\n{footer}"

    lines = [f"DevPulse Daily - {date_str}", "-" * 28]

    ranked = list(top[:5])
    while ranked:
        candidate = _render_top(ranked)
        rendered_sleeper = _render_sleeper(sleeper) if sleeper_eligible(sleeper) else ""
        body = "\n\n".join(x for x in (candidate, rendered_sleeper,
                                       _render_releases(releases)) if x)
        if len("\n".join(lines)) + len(body) + len(footer) + 31 <= MAX_MESSAGE:
            lines.append(body)
            break
        ranked.pop()  # drop lowest-ranked top item first
    else:
        lines.append(_render_sleeper(sleeper) if sleeper_eligible(sleeper) else "")

    lines.append("-" * 28)
    lines.append(footer)
    return "\n".join(lines)


def sleeper_eligible(sleeper: tuple[Item, Judgment] | None) -> bool:
    if sleeper is None:
        return False
    item, j = sleeper
    if item.source == "github_release":
        return False
    return is_sleeper_eligible(j.quality, item.engagement_pct)


def _render_top(top: list[tuple[Item, Judgment]]) -> str:
    lines = ["TOP 5 FOR YOU"]
    for n, (item, j) in enumerate(top, 1):
        lines.append(f"{n}. {item.title} [{_label(item)}, {item.engagement}]")
        lines.append(f"   rel {j.relevance} | q {j.quality}")
        lines.append(f'   "{j.verdict}"')
    return "\n".join(lines)


def _render_sleeper(sleeper: tuple[Item, Judgment] | None) -> str:
    if sleeper is None:
        return ""
    item, j = sleeper
    pct = round(item.engagement_pct * 100)
    return (
        "SLEEPER PICK\n"
        f"{item.title} [{_label(item)}, {item.engagement}]\n"
        f"q {j.quality}, engagement bottom {pct}% of its source class\n"
        f'"{j.verdict}"'
    )


def _render_releases(releases: list[Item]) -> str:
    if not releases:
        return ""
    lines = ["NEW RELEASES"]
    for rel in releases[:5]:
        lines.append(f"- {rel.title} ({rel.context})")
    return "\n".join(lines)

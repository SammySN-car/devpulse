# src/devpulse/pipeline.py
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .collectors.devto import collect_articles
from .collectors.github import collect_releases, collect_rising
from .collectors.hackernews import collect_show_hn, collect_top
from .judge import OllamaJudge, batch_judge, free_ram_mb
from .models import Item, Judgment, utcnow_iso
from .normalize import engagement_percentile, url_hash
from .store import Store


@dataclass
class DigestStats:
    scanned: int
    judged: int
    skipped_reason: str | None
    minutes: float


def _default_chain(token: str | None, watchlist: Sequence[str]) -> list[Callable[[], list[Item]]]:
    return [
        lambda: collect_rising(token=token),
        lambda: collect_releases(watchlist, token=token),
        collect_show_hn,
        collect_top,
        collect_articles,
    ]


def run_pipeline(
    store: Store,
    judge_factory: Callable[[], OllamaJudge],
    collectors: Sequence[Callable[[], list[Item]]] | None = None,
    token: str | None = None,
    watchlist: Sequence[str] = (),
    model: str = "qwen2.5:7b",
    *,
    free_ram: Callable[[], int] = free_ram_mb,
    guard_mb: int = 1500,
) -> DigestStats:
    started = time.monotonic()
    chain = list(collectors) if collectors is not None else _default_chain(token, watchlist)
    raw: list[Item] = []
    for collect in chain:
        try:
            raw.extend(collect())
        except Exception:
            continue  # source isolation: one failure never aborts the run

    # dedupe across sources by url identity
    unique: dict[str, Item] = {}
    for item in raw:
        if item.url:
            unique.setdefault(url_hash(item.url), item)
    items = list(unique.values())

    # engagement percentile within each source group
    by_source: dict[str, list[int]] = {}
    for item in items:
        by_source.setdefault(item.source, []).append(item.engagement)
    for item in items:
        item.engagement_pct = engagement_percentile(
            item.engagement, by_source[item.source])

    store.insert_items(items)
    pending = [item for _h, item in store.items_missing_judgment()]

    if not pending:
        stats = DigestStats(scanned=len(items), judged=0,
                            skipped_reason="no new items",
                            minutes=(time.monotonic() - started) / 60)
        store.record_digest(stats.scanned, stats.judged, stats.skipped_reason)
        return stats

    results, skipped = batch_judge(pending, judge_factory(),
                                   guard_mb=guard_mb, free_ram=free_ram)
    for item, (relevance, quality, verdict) in results:
        store.save_judgment(Judgment(
            url_hash=url_hash(item.url),
            relevance=relevance, quality=quality, verdict=verdict,
            model=model, prompt_version="v3.1",
            judged_at=utcnow_iso(),
        ))
    stats = DigestStats(scanned=len(items), judged=len(results),
                        skipped_reason=skipped,
                        minutes=(time.monotonic() - started) / 60)
    store.record_digest(stats.scanned, stats.judged, stats.skipped_reason)
    return stats

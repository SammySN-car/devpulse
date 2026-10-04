# tests/test_pipeline.py
from devpulse.models import Item
from devpulse.pipeline import run_pipeline
from devpulse.store import Store


def _item(url, source="hackernews", engagement=100, title="t"):
    return Item(url=url, title=title, source=source, engagement=engagement,
                context="c", fetched_at="2026-10-03T00:00:00+00:00")


class FakeJudge:
    def __init__(self):
        self.unloaded = False

    def judge(self, item):
        return (8, 9, "evaluated. yes")

    def unload(self):
        self.unloaded = True


def test_isolates_raising_collector_and_judges_deduped_items():
    store = Store()
    store.init_schema()

    def exploding():
        raise RuntimeError("source down")

    def good():
        return [_item("https://a/1", source="hackernews", engagement=100),
                _item("https://a/1?utm_source=x", source="hackernews", engagement=100)]

    stats = run_pipeline(store, judge_factory=FakeJudge,
                         collectors=[exploding, good],
                         free_ram=lambda: 9999)
    assert stats.scanned == 1  # duplicates collapsed, explosion ignored
    assert stats.judged == 1
    assert stats.skipped_reason is None
    rows = store.judged_rows()
    assert len(rows) == 1
    assert rows[0][1].quality == 9 and rows[0][1].model == "qwen2.5:7b"
    assert store.last_digest() is not None
    # a second run judges nothing new
    stats2 = run_pipeline(store, judge_factory=FakeJudge, collectors=[good],
                          free_ram=lambda: 9999)
    assert stats2.judged == 0


def test_no_new_items_and_guard_reasons():
    store = Store()
    store.init_schema()
    stats = run_pipeline(store, judge_factory=FakeJudge, collectors=[lambda: []])
    assert stats.skipped_reason == "no new items"
    assert store.last_digest()[3] == "no new items"


def test_percentile_computed_within_source_group():
    store = Store()
    store.init_schema()
    run_pipeline(
        store,
        judge_factory=FakeJudge,
        collectors=[lambda: [
            _item("https://g/1", source="github_rising", engagement=10, title="low"),
            _item("https://g/2", source="github_rising", engagement=900, title="high"),
            _item("https://h/1", source="hackernews", engagement=5, title="hn only"),
        ]],
        free_ram=lambda: 9999,
    )
    pending_after = store.search("")  # unused; read raw instead
    conn = store.conn
    pcts = {r["title"]: r["engagement_pct"]
            for r in conn.execute("SELECT title, engagement_pct FROM items")}
    assert pcts["low"] == 0.0     # nothing in its source group is strictly lower
    assert pcts["high"] == 0.5    # exactly one of two github_rising items is lower
    assert pcts["hn only"] == 0.0  # single-item group is neutral-eligible by design
    assert pending_after is not None


def test_guard_reason_blocks_judging_when_ram_low():
    store = Store()
    store.init_schema()

    def good():
        return [_item("https://a/1")]

    stats = run_pipeline(store, judge_factory=FakeJudge, collectors=[good],
                         free_ram=lambda: 1499)
    assert stats.judged == 0
    assert stats.skipped_reason == "judge unavailable (free RAM below guard)"
    assert store.judged_rows() == []

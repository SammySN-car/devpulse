# tests/test_store.py
from devpulse.models import Item, Judgment
from devpulse.store import Store


def _item(url, source="hackernews", engagement=100, pct=0.0, title="t"):
    return Item(url=url, title=title, source=source, engagement=engagement,
                context="c", fetched_at="2026-10-03T00:00:00+00:00", engagement_pct=pct)


def _judge(store, quality, relevance=7, verdict="v"):
    _h, item = store.items_missing_judgment()[0]
    store.save_judgment(Judgment(url_hash=_h, relevance=relevance, quality=quality,
                                 verdict=verdict, model="qwen2.5:7b", prompt_version="v3.1",
                                 judged_at="2026-10-03T00:01:00+00:00"))
    return item


def test_insert_is_idempotent_and_pending_reflects_judgments():
    s = Store()
    s.init_schema()
    s.insert_items([_item("https://a.example/x"), _item("https://a.example/x?utm_source=z")])
    pending = s.items_missing_judgment()
    assert len(pending) == 1
    h, item = pending[0]
    assert item.title == "t"
    s.save_judgment(Judgment(url_hash=h, relevance=8, quality=8, verdict="v",
                             model="qwen2.5:7b", prompt_version="v3.1",
                             judged_at="2026-10-03T00:01:00+00:00"))
    assert s.items_missing_judgment() == []
    s.insert_items([_item("https://a.example/x")])
    assert s.items_missing_judgment() == []


def test_sleepers_apply_gate_and_order():
    s = Store()
    s.init_schema()
    s.insert_items([
        _item("https://a/1", engagement=5, pct=0.1, title="best"),
        _item("https://a/2", engagement=5, pct=0.1, title="ok"),
        _item("https://a/3", engagement=5, pct=0.9, title="hyped"),
        _item("https://a/4", engagement=5, pct=0.1, title="mediocre"),
        _item("https://a/rel", source="github_release", pct=0.0, title="release"),
    ])
    for quality in (7, 9, 9, 6, 8):
        _judge(s, quality)
    titles = [it.title for it, _j in s.sleepers()]
    assert titles == ["ok", "best"]  # q9 first; q6 below gate; pct 0.9 excluded; release excluded
    assert all(j.quality >= 7 for _it, j in s.sleepers())


def test_releases_search_and_digest_log():
    s = Store()
    s.init_schema()
    s.insert_items([
        _item("https://a/rel", source="github_release", title="ollama v0.5"),
        _item("https://a/post", source="devto", title="FastAPI caching guide"),
    ])
    assert [i.title for i in s.releases()] == ["ollama v0.5"]
    _judge(s, 8)
    assert len(s.search("fastapi")) == 1
    assert s.last_digest() is None
    s.record_digest(42, 18, None)
    row = s.last_digest()
    assert row is not None and row[1] == 42 and row[3] is None

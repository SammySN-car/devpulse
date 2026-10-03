import json
from pathlib import Path

import httpx

from devpulse.collectors.hackernews import collect_show_hn, collect_top

FIXTURES = Path(__file__).parent / "fixtures"


def _transport(name: str, status_code: int = 200):
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return httpx.MockTransport(lambda request: httpx.Response(status_code, json=payload))


def test_show_hn_parses_and_builds_fallback_url():
    items = collect_show_hn(transport=_transport("hn_show.json"))
    assert len(items) == 2
    assert items[0].title == "Show HN: A tool I built"
    assert items[0].engagement == 3531
    assert items[0].context == "link domain: example.com"
    assert items[1].url == "https://news.ycombinator.com/item?id=2"
    assert all(i.source == "hackernews" for i in items)


def test_top_parses():
    items = collect_top(transport=_transport("hn_top.json"))
    assert [i.engagement for i in items] == [400]
    assert items[0].url.startswith("https://blog.example.org/")


def test_returns_empty_on_504():
    assert collect_show_hn(transport=_transport("hn_show.json", 504)) == []
    assert collect_top(transport=_transport("hn_top.json", 504)) == []

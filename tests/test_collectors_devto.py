# tests/test_collectors_devto.py
import json
from pathlib import Path

import httpx

from devpulse.collectors.devto import collect_articles

FIXTURES = Path(__file__).parent / "fixtures"


def _transport(status_code: int = 200):
    payload = json.loads((FIXTURES / "devto_articles.json").read_text(encoding="utf-8"))
    return httpx.MockTransport(lambda request: httpx.Response(status_code, json=payload))


def test_parses_articles():
    items = collect_articles(transport=_transport())
    assert [i.title for i in items] == ["FastAPI caching done right", "Short one"]
    assert items[0].source == "devto"
    assert items[0].engagement == 152
    assert items[0].context.startswith("published 2026-10-02")
    assert "(no description)" in items[1].context


def test_returns_empty_on_500():
    assert collect_articles(transport=_transport(500)) == []

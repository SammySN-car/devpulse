import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from devpulse.collectors.github import collect_releases, collect_rising

FIXTURES = Path(__file__).parent / "fixtures"


def _transport(name: str, status_code: int = 200, capture: list | None = None):
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


def test_rising_uses_absolute_created_date_and_parses_items():
    seen: list[httpx.Request] = []
    items = collect_rising(transport=_transport("github_rising.json", capture=seen),
                           today=date(2026, 10, 3))
    assert seen[0].url.params["q"] == "created:>2026-09-26 stars:>20"
    assert [i.title for i in items] == ["alice/tiny-linter", "bob/vibes"]
    assert items[0].engagement == 2571 and items[0].source == "github_rising"
    assert "no description provided" in items[1].context
    assert items[1].engagement == 88


def test_rising_returns_empty_on_503():
    assert collect_rising(transport=_transport("github_rising.json", 503)) == []


def test_releases_filters_by_window():
    items = collect_releases(
        ["ollama/ollama"],
        transport=_transport("github_releases.json"),
        now=datetime(2026, 10, 3, 6, 0, tzinfo=UTC),
    )
    assert [i.title for i in items] == ["ollama/ollama v0.5.0"]
    assert items[0].source == "github_release"
    assert "new model support" in items[0].context


def test_releases_empty_watchlist_and_error_path():
    assert collect_releases([], transport=_transport("github_releases.json")) == []
    assert collect_releases(["a/b"],
                            transport=_transport("github_releases.json", 403)) == []

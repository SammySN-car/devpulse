# tests/test_bot.py
from datetime import datetime

from devpulse.bot import (
    _first_ready,
    build_run_digest,
    can_refresh,
    cmd_dig,
    cmd_releases,
    cmd_sleeper,
    cmd_status,
    safe_run,
    seconds_until,
)
from devpulse.models import Item, Judgment, utcnow_iso
from devpulse.settings import Settings
from devpulse.store import Store


def _seed(store, title="carol/sleeper", quality=9, pct=0.2, source="github_rising"):
    store.insert_items([Item(url=f"https://x/{title}", title=title, source=source,
                             engagement=10, context="fastapi related",
                             fetched_at="2026-10-03T00:00:00+00:00", engagement_pct=pct)])
    h, _item = store.items_missing_judgment()[-1]
    store.save_judgment(Judgment(url_hash=h, relevance=8, quality=quality,
                                 verdict="underrated gem. yes", model="m",
                                 prompt_version="v3.1",
                                 judged_at=utcnow_iso()))


def _store():
    s = Store()
    s.init_schema()
    return s


def test_can_refresh_owner_only():
    assert can_refresh(7, 7) is True
    assert can_refresh(8, 7) is False
    assert can_refresh(8, None) is False


def test_seconds_until_rolls_over_to_next_day():
    assert seconds_until("07:00", datetime(2026, 10, 3, 6, 0)) == 3600.0
    assert seconds_until("07:00", datetime(2026, 10, 3, 8, 0)) == 23 * 3600.0
    assert seconds_until("07:00", datetime(2026, 10, 3, 7, 0)) == 86400.0


def test_commands_read_store():
    s = _store()
    _seed(s)
    assert "carol/sleeper" in cmd_sleeper(s)
    assert "q 9" in cmd_sleeper(s)
    assert "carol/sleeper" in cmd_dig(s, "fastapi")
    assert "no stored verdicts" in cmd_dig(s, "quantum")
    assert "no new watchlist releases" in cmd_releases(s)
    assert "no digest runs yet" in cmd_status(s)
    s.record_digest(10, 5, None)
    assert "10 scanned, 5 judged" in cmd_status(s)


def test_cmd_releases_appends_release_url():
    s = _store()
    url = "https://github.com/langchain-ai/langchain/releases/tag/v1.2.3"
    s.insert_items([Item(url=url, title="langchain v1.2.3", source="github_release",
                         engagement=500, context="release notes",
                         fetched_at="2026-10-03T00:00:00+00:00")])
    out = cmd_releases(s)
    assert "recent releases:" in out
    assert "langchain v1.2.3" in out
    assert url in out
    assert f"- langchain v1.2.3 {url}" in out


def test_safe_run_never_raises():
    def boom():
        raise RuntimeError("ollama down")

    assert safe_run(boom) == "daily run skipped: ollama down"
    assert safe_run(lambda: "ok") == "ok"


def test_first_ready_transitions_once():
    state: dict[str, bool] = {}
    assert _first_ready(state) is True
    assert _first_ready(state) is False


def test_build_run_digest_composes_full_message():
    s = _store()
    settings = Settings(discord_token="t", digest_channel_id=1,
                        watchlist=("a/b",), model="qwen2.5:7b")

    class FakeJudge:
        def judge(self, item):
            return (8, 9, "actually useful. yes")

        def unload(self):
            pass

    run = build_run_digest(
        settings, s,
        collectors=[lambda: [Item(url="https://x/y", title="alice/tool",
                                  source="github_rising", engagement=50,
                                  context="c", fetched_at="2026-10-03T00:00:00+00:00")]],
        judge_factory=FakeJudge,
        free_ram=lambda: 9999,
    )
    msg = run()
    assert "DevPulse Daily -" in msg
    assert "TOP 5 FOR YOU" in msg and "alice/tool" in msg
    assert "on-device" in msg


def test_build_run_digest_ranks_by_relevance_then_quality():
    s = _store()
    settings = Settings(discord_token="t", digest_channel_id=1,
                        watchlist=("a/b",), model="qwen2.5:7b")

    class RankedJudge:
        def judge(self, item):
            table = {"rank-low": (3, 9), "rank-mid": (7, 7),
                     "rank-tie": (7, 9), "rank-high": (9, 8)}
            rel, qual = table[item.title]
            return (rel, qual, "verdict. yes")

        def unload(self):
            pass

    def scramble():
        return [Item(url=f"https://x/{t}", title=t, source="github_rising",
                     engagement=10, context="c",
                     fetched_at="2026-10-03T00:00:00+00:00")
                for t in ("rank-low", "rank-mid", "rank-tie", "rank-high")]

    run = build_run_digest(settings, s, collectors=[scramble],
                           judge_factory=RankedJudge,
                           free_ram=lambda: 9999)
    msg = run()
    order = [msg.index(t)
             for t in ("rank-high", "rank-tie", "rank-mid", "rank-low")]
    assert order == sorted(order)


def test_release_stays_out_of_top_but_appears_in_releases():
    s = _store()
    settings = Settings(discord_token="t", digest_channel_id=1,
                        watchlist=("a/b",), model="qwen2.5:7b")
    release_title = "ollama/ollama v9.9"

    class ReleaseJudge:
        def judge(self, item):
            if item.source == "github_release":
                return (10, 10, "shipped. yes")
            return (8, 8, "useful. yes")

        def unload(self):
            pass

    def collect():
        items = [Item(url=f"https://x/reg-{n}", title=f"reg-{n}", source="github_rising",
                      engagement=10 * n, context="c",
                      fetched_at="2026-10-03T00:00:00+00:00")
                 for n in range(1, 7)]
        items.append(Item(url="https://x/rel", title=release_title, source="github_release",
                          engagement=500, context="v9.9",
                          fetched_at="2026-10-03T00:00:00+00:00"))
        return items

    run = build_run_digest(settings, s, collectors=[collect],
                           judge_factory=ReleaseJudge,
                           free_ram=lambda: 9999)
    msg = run()
    assert release_title in msg
    assert s.items_missing_judgment() == []  # release left the pending state
    assert msg.index("NEW RELEASES") < msg.index(release_title)

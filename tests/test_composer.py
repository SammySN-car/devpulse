# tests/test_composer.py
import re

from devpulse.composer import compose_digest
from devpulse.models import Item, Judgment
from devpulse.pipeline import DigestStats

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")


def _row(title, source="github_rising", engagement=100, pct=0.1,
         quality=8, relevance=8, verdict="solid tool. worth clicking yes"):
    item = Item(url=f"https://x/{title}", title=title, source=source,
                engagement=engagement, context="c",
                fetched_at="2026-10-03T00:00:00+00:00", engagement_pct=pct)
    j = Judgment(url_hash="h", relevance=relevance, quality=quality, verdict=verdict,
                 model="qwen2.5:7b", prompt_version="v3.1")
    return item, j


def _stats(scanned=42, judged=18, reason=None, minutes=6.4):
    return DigestStats(scanned=scanned, judged=judged, skipped_reason=reason,
                       minutes=minutes)


def test_full_digest_exact_layout_no_emoji():
    msg = compose_digest(
        date_str="2026-10-04",
        top=[_row("alice/tiny-linter", engagement=2571), _row("bob/tool", engagement=88)],
        sleeper=_row("carol/sleeper", engagement=5, pct=0.2, quality=9),
        releases=[Item(url="https://r", title="ollama v0.5", source="github_release",
                       engagement=1, context="release body: notes",
                       fetched_at="2026-10-03")],
        stats=_stats(),
        model="qwen2.5:7b",
    )
    assert msg.splitlines()[0] == "DevPulse Daily - 2026-10-04"
    assert "TOP 5 FOR YOU" in msg
    assert "1. alice/tiny-linter [github, 2571]" in msg
    assert "rel 8 | q 8" in msg
    assert "SLEEPER PICK" in msg
    assert "carol/sleeper" in msg
    assert "NEW RELEASES" in msg and "ollama v0.5" in msg
    assert "- ollama v0.5 (release body: notes) https://r" in msg
    assert "42 scanned, 18 judged, 6.4 min, qwen2.5:7b, on-device" in msg
    assert not _EMOJI.search(msg)


def _release_line(url):
    msg = compose_digest(
        "d", top=[], sleeper=None,
        releases=[Item(url=url, title="langchain v1.2.3", source="github_release",
                       engagement=1, context="release notes",
                       fetched_at="2026-10-03")],
        stats=_stats(judged=1), model="m",
    )
    return next(line for line in msg.splitlines() if "langchain" in line)


def test_release_line_appends_bare_url():
    url = "https://github.com/langchain-ai/langchain/releases/tag/v1.2.3"
    assert _release_line(url) == f"- langchain v1.2.3 (release notes) {url}"


def test_release_line_empty_url_adds_nothing():
    line = _release_line("")
    assert line == "- langchain v1.2.3 (release notes)"
    assert not line.endswith(" ")


def test_sleeper_section_uses_gate_and_omits_when_ineligible():
    # quality below gate: composer must not present it as a sleeper pick
    item, j = _row("nope", quality=6, pct=0.1)
    msg = compose_digest("d", top=[], sleeper=(item, j), releases=[],
                         stats=_stats(judged=1), model="m")
    assert "SLEEPER PICK" not in msg
    msg2 = compose_digest("d", top=[], sleeper=None, releases=[],
                          stats=_stats(judged=0), model="m")
    assert "SLEEPER PICK" not in msg2


def test_overflow_drops_top_items_keeps_sleeper_and_footer():
    top = [(_row(title=f"repo-{i}", verdict="x" * 300)[0],
            _row(title=f"repo-{i}", verdict="x" * 300)[1]) for i in range(5)]
    msg = compose_digest("d", top=top,
                         sleeper=_row("sleeper-kept", verdict="y" * 300),
                         releases=[], stats=_stats(), model="m")
    assert len(msg) <= 1900
    assert "sleeper-kept" in msg
    assert "on-device" in msg


def test_render_caps_title_and_verdict():
    item, j = _row("t" * 400, verdict="v" * 1000)
    msg = compose_digest("d", top=[(item, j)], sleeper=None, releases=[],
                         stats=_stats(), model="m")
    assert len(msg) <= 1900
    assert "v" * 301 not in msg
    assert "t" * 151 not in msg
    assert "..." in msg


def test_fallback_keeps_releases_when_they_fit():
    msg = compose_digest("d", top=[], sleeper=_row("sleeper-kept"),
                         releases=[Item(url="https://r", title="ollama v0.5",
                                        source="github_release", engagement=1,
                                        context="release body: notes",
                                        fetched_at="2026-10-03")],
                         stats=_stats(), model="m")
    assert "sleeper-kept" in msg
    assert "ollama v0.5" in msg
    assert len(msg) <= 1900


def test_fallback_overflow_drops_releases_keeps_sleeper():
    big = [Item(url=f"https://r/{i}", title=f"rel-{i}", source="github_release",
                engagement=1, context="c" * 400, fetched_at="2026-10-03")
           for i in range(5)]
    msg = compose_digest("d", top=[], sleeper=_row("sleeper-kept"),
                         releases=big, stats=_stats(), model="m")
    assert "sleeper-kept" in msg
    assert "rel-0" not in msg
    assert len(msg) <= 1900


def test_no_new_items_and_skip_messages():
    msg = compose_digest("d", top=[], sleeper=None, releases=[],
                         stats=_stats(scanned=42, judged=0, reason="no new items"),
                         model="m")
    assert msg.startswith("no new items worth your time today")
    assert "42 scanned, 0 judged" in msg
    msg2 = compose_digest("d", top=[], sleeper=None, releases=[],
                          stats=_stats(reason="judge unavailable (free RAM below guard)"),
                          model="m")
    assert msg2.startswith("daily run skipped: judge unavailable")
    msg3 = compose_digest("d", top=[], sleeper=None, releases=[],
                          stats=_stats(reason="no new items"), model="m")
    assert "all sources" not in msg3

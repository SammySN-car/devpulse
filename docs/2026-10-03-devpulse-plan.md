# devpulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Discord bot that collects fresh tech items from free sources, judges them with a locally-run qwen2.5:7b (Ollama), and posts a daily digest with top picks, a deterministic sleeper pick, and watchlist releases.

**Architecture:** Collectors (one isolated module per source) -> normalizer (URL identity + engagement percentile) -> SQLite diff (judge each URL once) -> sequential RAM-guarded judge (Ollama JSON mode, prompt v3.1) -> deterministic sleeper scoring in code -> digest composer -> discord.py embed-free text message + slash commands that read SQLite only.

**Tech Stack:** Python 3.11+, discord.py, httpx, python-dotenv, psutil, SQLite (stdlib), pytest, ruff. CI: GitHub Actions (Ubuntu + Windows).

**Spec:** `docs/2026-10-03-devpulse-design.md` - the plan argues from the spec; executors read both.

## Global Constraints

- No emojis anywhere: code, messages, README, tests. Outbound strings are regex-tested for emoji ranges.
- Judge model: `qwen2.5:7b` at `http://localhost:11434`, JSON mode, `temperature 0.2`, `num_ctx 2048`, prompt version constant `PROMPT_VERSION = "v3.1"` (spike v3 + English-only rule), verdicts always English.
- Judging is strictly sequential; batch aborts when free RAM < 1500 MB; model is unloaded with `keep_alive: 0` after every batch (failure or success).
- Sleeper formula lives in code only: `sleeper_score = quality * (1 - engagement_pct)`; eligible iff `quality >= 7 AND engagement_pct <= 0.40`; releases are never sleeper candidates.
- Sources allowed: GitHub API, HN (Algolia), dev.to. No Twitter, no Reddit, no scraping of ToS-protected sites.
- Never commit: `.env`, `*.db`, `*.log`, output dumps.
- Docs stay flat under `docs/` (no nested `superpowers/` folders).
- Dependencies (runtime): `discord.py>=2.4`, `httpx>=0.27`, `python-dotenv>=1.0`, `psutil>=6.0`. Dev: `pytest>=8.0`, `ruff>=0.6`. No others without updating the spec.
- CI runs `ruff check .` and `pytest -v` (default excludes `-m live`) on ubuntu-latest and windows-latest.
- Submission deadline 2026-10-05 06:59 UTC: no scope additions (non-goals in spec section 2 win every argument).

## Review Focus

Failure modes the spec implies but no single task owns. Each line names its pinning test.

1. **Ollama returns valid JSON of the wrong shape** (string scores, missing `verdict`, scores outside 0-10) - a reasonable parser must coerce strings and reject the rest, not crash the batch: Task 6 `parse_judgment` tests.
2. **RAM guard boundary and units** (MB not bytes; exactly 1500 MB must proceed, 1499 must abort): Task 6 `batch_judge` tests with injected `free_ram`.
3. **A source endpoint returns 503/timeout** - the run must continue with an empty list for that source, never raise out of the pipeline: Tasks 7/8/9 MockTransport 503 tests + Task 10 collector-isolation test.
4. **Percentile degenerate groups** (single-item batch, ties, empty group) - sleeper eligibility must be deterministic: Task 3 `engagement_percentile` tests.
5. **Discord 2000-character message limit** - a full digest with five verbose verdicts overflows silently at send time: Task 11 truncation test (plus the no-emoji regex test in the same task).

## File Structure

```
devpulse/
  pyproject.toml                      project metadata, ruff + pytest config
  .env.example                        tokens/channel/model/watchlist template
  .github/workflows/ci.yml            ruff + pytest matrix
  src/devpulse/
    __init__.py                       __version__
    models.py                         Item, Judgment dataclasses, utcnow_iso()
    settings.py                       Settings dataclass + load_settings()
    normalize.py                      normalize_url, url_hash, engagement_percentile
    scoring.py                        sleeper_score, is_sleeper_eligible
    store.py                          Store class over sqlite3, schema, queries
    judge.py                          prompt v3.1, parse, OllamaJudge, batch guard
    collectors/
      __init__.py                     DEFAULT_COLLECTORS registry
      github.py                       collect_rising, collect_releases
      hackernews.py                   collect_show_hn, collect_top
      devto.py                        collect_articles
    pipeline.py                       run_pipeline orchestrator + DigestStats
    composer.py                       compose_digest (exact message text)
    bot.py                            slash-command handlers, scheduler, build_bot
    main.py                           entry point: settings -> store -> bot.run
  tests/
    conftest.py                       fixtures: sample Item/Judgment, tmp Store
    fixtures/github_rising.json       captured API payloads
    fixtures/github_releases.json
    fixtures/hn_show.json
    fixtures/hn_top.json
    fixtures/devto_articles.json
    test_scaffold.py ... test_bot.py  one test module per task
  docs/
    2026-10-03-devpulse-design.md      spec
    2026-10-03-devpulse-plan.md        this plan
  spikes/prototype_judge.py           throwaway evidence, never imported
```

Dependency order: 1 -> 2 -> (3, 4) -> 5 -> 6 -> (7, 8, 9) -> 10 -> 11 -> 12 -> 13.

---

### Task 1: Scaffold

**Files:**
- Create: `pyproject.toml`, `.github/workflows/ci.yml`, `src/devpulse/__init__.py`, `tests/test_scaffold.py`

**Interfaces:**
- Produces: installable package `devpulse` with `__version__: str`; pytest marker `live`; default `pytest` run excludes `live`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold.py
def test_package_importable():
    import devpulse

    assert devpulse.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scaffold.py -v`
Expected: FAIL (module `devpulse` not found / no tests collected before install)

- [ ] **Step 3: Write pyproject and package init**

```toml
# pyproject.toml
[project]
name = "devpulse"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "discord.py>=2.4",
    "httpx>=0.27",
    "python-dotenv>=1.0",
    "psutil>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not live'"
markers = [
    "live: hits real network or local Ollama; excluded by default",
]
```

```python
# src/devpulse/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 4: Install and run**

Run: `python -m pip install -e ".[dev]"` then `python -m pytest tests/test_scaffold.py -v` then `ruff check .`
Expected: install OK, test PASS, ruff reports no issues (empty package).

- [ ] **Step 5: Add CI workflow**

```yaml
# .github/workflows/ci.yml
name: ci
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install -e ".[dev]"
      - run: ruff check .
      - run: python -m pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .github/ src/ tests/
git commit -m "chore: scaffold package, tooling, and CI"
```

---

### Task 2: Settings

**Files:**
- Create: `src/devpulse/settings.py`, `tests/test_settings.py`
- Modify: `.env.example` (add `DISCORD_OWNER_ID`)

**Interfaces:**
- Produces: `Settings` frozen dataclass with fields `discord_token: str`, `digest_channel_id: int`, `digest_time: str` ("HH:MM"), `model: str`, `watchlist: tuple[str, ...]`, `github_token: str | None`, `owner_id: int | None`; `load_settings(env_path: str = ".env") -> Settings`. Raises `ValueError` on malformed `DIGEST_TIME`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_settings.py
from dataclasses import FrozenInstanceError

import pytest

from devpulse.settings import Settings, load_settings


def test_parses_all_fields(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "DISCORD_BOT_TOKEN=abc123\n"
        "DIGEST_CHANNEL_ID=42\n"
        "DIGEST_TIME=06:30\n"
        "MODEL=qwen2.5:7b\n"
        "WATCHLIST=ollama/ollama, langchain-ai/langchain\n"
        "GITHUB_TOKEN=ghp_x\n"
        "DISCORD_OWNER_ID=7\n",
        encoding="utf-8",
    )
    s = load_settings(str(env))
    assert s.discord_token == "abc123"
    assert s.digest_channel_id == 42
    assert s.digest_time == "06:30"
    assert s.model == "qwen2.5:7b"
    assert s.watchlist == ("ollama/ollama", "langchain-ai/langchain")
    assert s.github_token == "ghp_x"
    assert s.owner_id == 7


def test_empty_watchlist_and_missing_optional_tokens(tmp_path):
    env = tmp_path / ".env"
    env.write_text("DISCORD_BOT_TOKEN=t\nDIGEST_CHANNEL_ID=1\n", encoding="utf-8")
    s = load_settings(str(env))
    assert s.watchlist == ()
    assert s.github_token is None
    assert s.owner_id is None
    assert s.model == "qwen2.5:7b"
    assert s.digest_time == "07:00"


def test_rejects_malformed_digest_time(tmp_path):
    env = tmp_path / ".env"
    env.write_text("DISCORD_BOT_TOKEN=t\nDIGEST_CHANNEL_ID=1\nDIGEST_TIME=7am\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(str(env))


def test_is_frozen():
    s = Settings(discord_token="t", digest_channel_id=1)
    with pytest.raises(FrozenInstanceError):
        s.discord_token = "other"  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_settings.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.settings'`

- [ ] **Step 3: Implement**

```python
# src/devpulse/settings.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@dataclass(frozen=True)
class Settings:
    discord_token: str
    digest_channel_id: int
    digest_time: str = "07:00"
    model: str = "qwen2.5:7b"
    watchlist: tuple[str, ...] = ()
    github_token: str | None = None
    owner_id: int | None = None


def load_settings(env_path: str = ".env") -> Settings:
    load_dotenv(env_path, override=True)
    digest_time = os.environ.get("DIGEST_TIME", "07:00")
    if not _TIME_RE.match(digest_time):
        raise ValueError(f"DIGEST_TIME must be HH:MM, got {digest_time!r}")
    raw = os.environ.get("WATCHLIST", "")
    watchlist = tuple(p.strip() for p in raw.split(",") if p.strip())
    owner = os.environ.get("DISCORD_OWNER_ID", "").strip()
    return Settings(
        discord_token=os.environ.get("DISCORD_BOT_TOKEN", ""),
        digest_channel_id=int(os.environ.get("DIGEST_CHANNEL_ID", "0") or 0),
        digest_time=digest_time,
        model=os.environ.get("MODEL", "qwen2.5:7b"),
        watchlist=watchlist,
        github_token=os.environ.get("GITHUB_TOKEN", "").strip() or None,
        owner_id=int(owner) if owner else None,
    )
```

`.env.example` gains one line after `DIGEST_CHANNEL_ID=`:

```
# Bot owner (user id allowed to run /refresh)
DISCORD_OWNER_ID=
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_settings.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/devpulse/settings.py tests/test_settings.py .env.example
git commit -m "feat: load and validate settings from .env"
```

---

### Task 3: Normalizer

**Files:**
- Create: `src/devpulse/normalize.py`, `tests/test_normalize.py`, `src/devpulse/models.py`

**Interfaces:**
- Consumes: none (first data-shape module).
- Produces: `Item(url: str, title: str, source: str, engagement: int, context: str, fetched_at: str, engagement_pct: float = 0.0)` and `Judgment(url_hash: str, relevance: int, quality: int, verdict: str, model: str, prompt_version: str, status: str = "ok", judged_at: str = "")` dataclasses; `utcnow_iso() -> str`; `normalize_url(url: str) -> str`; `url_hash(url: str) -> str` (sha256 hex of normalized url); `engagement_percentile(engagement: int, group: list[int]) -> float` = share of the group with strictly lower engagement, `0.0` for empty group.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_normalize.py
from devpulse.models import Item
from devpulse.normalize import engagement_percentile, normalize_url, url_hash


def test_strips_tracking_params_and_normalizes():
    a = normalize_url("HTTPS://Example.COM/path/?utm_source=x&keep=1&fbclid=zzz")
    assert a == "https://example.com/path?keep=1"


def test_trailing_slash_removed_and_hash_stable_across_variants():
    v1 = "https://example.com/post/"
    v2 = "https://example.com/post?utm_campaign=tw"
    assert normalize_url(v1) == normalize_url(v2)
    assert url_hash(v1) == url_hash(v2)
    assert len(url_hash(v1)) == 64


def test_percentile_counts_strictly_lower():
    assert engagement_percentile(25, [10, 20, 30]) == 2 / 3
    assert engagement_percentile(0, [10, 20]) == 0.0


def test_percentile_degenerate_groups():
    assert engagement_percentile(5, [5]) == 0.0
    assert engagement_percentile(10, [10, 10]) == 0.0
    assert engagement_percentile(99, []) == 0.0


def test_item_defaults():
    it = Item(url="u", title="t", source="devto", engagement=1, context="c", fetched_at="now")
    assert it.engagement_pct == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_normalize.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.models'`

- [ ] **Step 3: Implement**

```python
# src/devpulse/models.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Item:
    url: str
    title: str
    source: str
    engagement: int
    context: str
    fetched_at: str
    engagement_pct: float = 0.0


@dataclass
class Judgment:
    url_hash: str
    relevance: int
    quality: int
    verdict: str
    model: str
    prompt_version: str
    status: str = "ok"
    judged_at: str = ""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
```

```python
# src/devpulse/normalize.py
from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "source", "fbclid", "gclid",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in _TRACKING]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), "")
    )


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def engagement_percentile(engagement: int, group: list[int]) -> float:
    if not group:
        return 0.0
    return sum(1 for e in group if e < engagement) / len(group)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_normalize.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/devpulse/models.py src/devpulse/normalize.py tests/test_normalize.py
git commit -m "feat: item models, url identity, engagement percentile"
```

---

### Task 4: Sleeper scoring

**Files:**
- Create: `src/devpulse/scoring.py`, `tests/test_scoring.py`

**Interfaces:**
- Consumes: none (pure functions).
- Produces: `sleeper_score(quality: int, engagement_pct: float) -> float`; `is_sleeper_eligible(quality: int, engagement_pct: float) -> bool` (gate `quality >= 7 and engagement_pct <= 0.40`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scoring.py
from devpulse.scoring import is_sleeper_eligible, sleeper_score


def test_formula():
    assert sleeper_score(8, 0.25) == 6.0
    assert sleeper_score(7, 0.0) == 7.0
    assert sleeper_score(10, 1.0) == 0.0


def test_gate_boundaries():
    assert is_sleeper_eligible(7, 0.40) is True
    assert is_sleeper_eligible(6, 0.0) is False
    assert is_sleeper_eligible(7, 0.41) is False
    assert is_sleeper_eligible(10, 1.0) is False
    assert is_sleeper_eligible(0, 0.0) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.scoring'`

- [ ] **Step 3: Implement**

```python
# src/devpulse/scoring.py
from __future__ import annotations

SLEEPER_MIN_QUALITY = 7
SLEEPER_MAX_ENGAGEMENT_PCT = 0.40


def sleeper_score(quality: int, engagement_pct: float) -> float:
    return quality * (1.0 - engagement_pct)


def is_sleeper_eligible(quality: int, engagement_pct: float) -> bool:
    return quality >= SLEEPER_MIN_QUALITY and engagement_pct <= SLEEPER_MAX_ENGAGEMENT_PCT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/devpulse/scoring.py tests/test_scoring.py
git commit -m "feat: deterministic sleeper score and eligibility gate"
```

---

### Task 5: Store (SQLite)

**Files:**
- Create: `src/devpulse/store.py`, `tests/test_store.py`
- Modify: `docs/2026-10-03-devpulse-design.md` (spec section 6 schema gains `engagement_pct REAL` - required so section 8's gate can be recomputed by `/sleeper` days later; explicit spec extension, noted here)

**Interfaces:**
- Consumes: `Item`, `Judgment` (Task 3).
- Produces: `Store(path: str = ":memory:")` with `init_schema()`, `insert_items(items: list[Item])` (INSERT OR IGNORE on url hash), `items_missing_judgment() -> list[tuple[str, Item]]`, `save_judgment(j: Judgment)`, `judged_rows(since_days: int = 7) -> list[tuple[Item, Judgment]]`, `sleepers(since_days: int = 7) -> list[tuple[Item, Judgment]]` (gate re-applied in SQL, releases excluded), `releases(limit: int = 10) -> list[Item]`, `search(term: str) -> list[tuple[Item, Judgment]]`, `last_digest() -> tuple | None`, `record_digest(item_count: int, judged_count: int, skipped_reason: str | None)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_store.py
from devpulse.models import Item, Judgment
from devpulse.store import Store


def _item(url, source="hackernews", engagement=100, pct=0.0, title="t"):
    return Item(url=url, title=title, source=source, engagement=engagement,
                context="c", fetched_at="2026-10-03T00:00:00+00:00", engagement_pct=pct)


def _judge(store, quality, relevance=7, verdict="v"):
    _h, item = store.items_missing_judgment()[-1]
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.store'`

- [ ] **Step 3: Update the spec schema block**

In `docs/2026-10-03-devpulse-design.md` section 6, add `engagement_pct REAL,` directly under `engagement INTEGER,` in the `items` table so code and spec stay in sync.

- [ ] **Step 4: Implement**

```python
# src/devpulse/store.py
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from .models import Item, Judgment
from .normalize import url_hash
from .scoring import SLEEPER_MAX_ENGAGEMENT_PCT, SLEEPER_MIN_QUALITY

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  url_hash TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  source TEXT NOT NULL,
  engagement INTEGER NOT NULL,
  engagement_pct REAL NOT NULL DEFAULT 0,
  context TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS judgments (
  url_hash TEXT PRIMARY KEY REFERENCES items(url_hash),
  relevance INTEGER NOT NULL,
  quality INTEGER NOT NULL,
  verdict TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ok',
  judged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS digests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  posted_at TEXT NOT NULL,
  item_count INTEGER NOT NULL,
  judged_count INTEGER NOT NULL,
  skipped_reason TEXT
);
"""


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def insert_items(self, items: list[Item]) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO items (url_hash, url, title, source, engagement,"
            " engagement_pct, context, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(url_hash(i.url), i.url, i.title, i.source, i.engagement,
              i.engagement_pct, i.context, i.fetched_at) for i in items],
        )
        self.conn.commit()

    def items_missing_judgment(self) -> list[tuple[str, Item]]:
        rows = self.conn.execute(
            "SELECT i.* FROM items i LEFT JOIN judgments j USING (url_hash)"
            " WHERE j.url_hash IS NULL ORDER BY i.fetched_at, i.url"
        ).fetchall()
        return [(r["url_hash"], _item_from_row(r)) for r in rows]

    def save_judgment(self, j: Judgment) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO judgments (url_hash, relevance, quality, verdict,"
            " model, prompt_version, status, judged_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (j.url_hash, j.relevance, j.quality, j.verdict, j.model,
             j.prompt_version, j.status, j.judged_at),
        )
        self.conn.commit()

    def judged_rows(self, since_days: int = 7) -> list[tuple[Item, Judgment]]:
        return self._joined("j.status = 'ok'", since_days)

    def sleepers(self, since_days: int = 7) -> list[tuple[Item, Judgment]]:
        return self._joined(
            "j.status = 'ok' AND j.quality >= ? AND i.engagement_pct <= ?"
            " AND i.source <> 'github_release'",
            since_days,
            params=(SLEEPER_MIN_QUALITY, SLEEPER_MAX_ENGAGEMENT_PCT),
        )

    def releases(self, limit: int = 10) -> list[Item]:
        rows = self.conn.execute(
            "SELECT * FROM items WHERE source = 'github_release'"
            " ORDER BY fetched_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_item_from_row(r) for r in rows]

    def search(self, term: str) -> list[tuple[Item, Judgment]]:
        like = f"%{term}%"
        return self._joined(
            "j.status = 'ok' AND (i.title LIKE ? OR i.context LIKE ?)",
            since_days=None, params=(like, like),
        )

    def last_digest(self) -> tuple | None:
        row = self.conn.execute(
            "SELECT id, item_count, judged_count, skipped_reason, posted_at"
            " FROM digests ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return tuple(row) if row else None

    def record_digest(self, item_count: int, judged_count: int,
                      skipped_reason: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO digests (posted_at, item_count, judged_count, skipped_reason)"
            " VALUES (?, ?, ?, ?)",
            (now, item_count, judged_count, skipped_reason),
        )
        self.conn.commit()

    def _joined(self, where: str, since_days: int | None, params: tuple = ()) -> list:
        sql = (
            "SELECT i.*, j.relevance, j.quality, j.verdict, j.model, j.prompt_version,"
            " j.status, j.judged_at FROM items i JOIN judgments j USING (url_hash)"
            f" WHERE {where}"
        )
        args = list(params)
        if since_days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
            sql += " AND j.judged_at >= ?"
            args.append(cutoff)
        sql += " ORDER BY j.quality DESC, i.engagement ASC"
        rows = self.conn.execute(sql, args).fetchall()
        return [(_item_from_row(r), _judgment_from_row(r)) for r in rows]


def _item_from_row(r: sqlite3.Row) -> Item:
    return Item(url=r["url"], title=r["title"], source=r["source"],
                engagement=r["engagement"], context=r["context"],
                fetched_at=r["fetched_at"], engagement_pct=r["engagement_pct"])


def _judgment_from_row(r: sqlite3.Row) -> Judgment:
    return Judgment(url_hash=r["url_hash"], relevance=r["relevance"], quality=r["quality"],
                    verdict=r["verdict"], model=r["model"], prompt_version=r["prompt_version"],
                    status=r["status"], judged_at=r["judged_at"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_store.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/devpulse/store.py tests/test_store.py docs/2026-10-03-devpulse-design.md
git commit -m "feat: sqlite store with diff, sleeper, search queries"
```

---

### Task 6: Judge (prompt v3.1, Ollama client, RAM guard)

**Files:**
- Create: `src/devpulse/judge.py`, `tests/test_judge.py`

**Interfaces:**
- Consumes: `Item` (Task 3).
- Produces: `PROMPT_VERSION = "v3.1"`; `render_prompt(item: Item) -> str`; `parse_judgment(raw: str) -> tuple[int, int, str]` (raises `ValueError`; coerces string scores; range-checks 0-10; collapses verdict newlines to ` | `); `OllamaJudge(model: str, base_url: str = "http://localhost:11434", transport: httpx.BaseTransport | None = None)` with `judge(item: Item) -> tuple[int, int, str] | None` (one retry, `None` on double failure) and `unload()`; `free_ram_mb() -> int`; `batch_judge(items, judge, guard_mb: int = 1500, free_ram: Callable[[], int] = free_ram_mb) -> tuple[list[tuple[Item, tuple[int, int, str]]], str | None]` (results, skipped_reason). Unloads the judge exactly once when `items` is non-empty; empty input returns `([], None)` without touching the model.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_judge.py
import json

import httpx
import pytest

from devpulse.judge import (
    PROMPT_VERSION, OllamaJudge, batch_judge, parse_judgment, render_prompt,
)
from devpulse.models import Item


def _item(title="feder-cr/dots", context="description: open-source agent | language: Python"):
    return Item(url="https://github.com/feder-cr/dots", title=title, source="github_rising",
                engagement=100, context=context, fetched_at="2026-10-03T00:00:00+00:00")


def test_render_prompt_contains_contract():
    p = render_prompt(_item())
    assert "feder-cr/dots" in p
    assert "open-source agent" in p
    assert "ALWAYS respond in English" in p
    assert "never invent features" in p
    assert '"relevance"' in p
    assert PROMPT_VERSION == "v3.1"


def test_parse_coerces_and_validates():
    rel, qual, verdict = parse_judgment(
        json.dumps({"relevance": "8", "quality": 7, "verdict": "line one\nline two"})
    )
    assert (rel, qual, verdict) == (8, 7, "line one | line two")
    for bad in (
        "not json",
        '"just a string"',
        json.dumps({"relevance": 8, "quality": 7}),
        json.dumps({"relevance": 11, "quality": 7, "verdict": "x"}),
        json.dumps({"relevance": 8, "quality": 7, "verdict": "  "}),
    ):
        with pytest.raises(ValueError):
            parse_judgment(bad)


def _judge_returning(bodies: list[str]) -> tuple[OllamaJudge, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        payload = json.loads(request.content)
        if payload.get("keep_alive") == 0:
            return httpx.Response(200, json={})
        body = bodies.pop(0) if bodies else "{}"
        return httpx.Response(200, json={"response": body})

    return OllamaJudge(model="qwen2.5:7b", transport=httpx.MockTransport(handler)), calls


def test_judge_retries_once_then_succeeds():
    judge, calls = _judge_returning([
        "garbage",
        json.dumps({"relevance": 8, "quality": 8, "verdict": "solid tool. yes"}),
    ])
    assert judge.judge(_item()) == (8, 8, "solid tool. yes")
    assert calls.count("/api/generate") == 2


def test_judge_returns_none_after_double_failure():
    judge, _calls = _judge_returning(["still garbage", "also garbage"])
    assert judge.judge(_item()) is None


def test_batch_guard_boundary_sequential_and_unload_once():
    judged: list[str] = []
    unloads: list[int] = []

    class FakeJudge:
        def judge(self, item):
            judged.append(item.title)
            return (8, 8, "v")

        def unload(self):
            unloads.append(1)

    items = [_item("a"), _item("b"), _item("c")]
    ram = iter([1600, 1500, 1499])
    results, skipped = batch_judge(items, FakeJudge(), guard_mb=1500, free_ram=lambda: next(ram))
    assert [i.title for i, _ in results] == ["a", "b"]  # 1500 exactly proceeds
    assert skipped and "guard" in skipped
    assert unloads == [1]

    ram2 = iter([1499])  # below guard aborts before judging
    results2, skipped2 = batch_judge([_item("x")], FakeJudge(), free_ram=lambda: next(ram2))
    assert results2 == [] and skipped2 and "guard" in skipped2

    assert batch_judge([], FakeJudge()) == ([], None)  # empty: no unload call made


@pytest.mark.live
def test_live_judgment_round_trip():
    judge = OllamaJudge(model="qwen2.5:7b")
    rel, qual, verdict = judge.judge(
        _item(title="psf/requests", context="description: Python HTTP library | language: Python")
    )
    judge.unload()
    assert 0 <= rel <= 10 and 0 <= qual <= 10
    assert isinstance(verdict, str) and verdict
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_judge.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.judge'` (live test deselected by default addopts)

- [ ] **Step 3: Implement**

```python
# src/devpulse/judge.py
from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import psutil

from .models import Item

PROMPT_VERSION = "v3.1"
OLLAMA_URL = "http://localhost:11434"

PROMPT_TEMPLATE = """You curate a daily digest for ONE developer: a Python/FastAPI/web dev who also builds AI tools.
Judge this item on the text provided. Use ONLY that text - never invent features.

ITEM
title: {title}
source: {source}
engagement: {engagement} (stars or upvotes - popularity only, NOT quality)
context: {context}

SCORING ANCHORS
relevance to THIS developer (0-10):
  0-2 = unrelated to their work | 3-4 = tangential | 5-6 = worth a glance |
  7-8 = directly useful this month | 9-10 = would change how they work
quality regardless of popularity (0-10):
  0-2 = junk, abandoned, or misleading | 3-4 = shallow demo |
  5-6 = solid but ordinary | 7-8 = crafted, novel, or unusually deep |
  9-10 = landmark

SCORING LOGIC (illustrations of reasoning - these are NOT items under review
and their wording must never appear in your verdict)
- A polished niche CLI, 40 stars, active commits, MIT -> relevance 8 (fits stack), quality 8 (real utility, low hype).
- A viral joke post, 3500 upvotes, no real artifact -> relevance 2, quality 3 (hype >> substance).
- Missing or ambiguous description -> do not guess features; verdict states what is missing.

OUTPUT (JSON only, verdict in exactly 2 short lines)
ALWAYS respond in English, even if the title is not.
{{"relevance": <int>, "quality": <int>, "verdict": "<line 1: what it ACTUALLY is/does, based only on provided text; line 2: worth clicking yes/no for this dev and why in a few words>"}}
"""


def render_prompt(item: Item) -> str:
    return PROMPT_TEMPLATE.format(
        title=item.title, source=item.source, engagement=item.engagement, context=item.context
    )


def parse_judgment(raw: str) -> tuple[int, int, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("response is not an object")
    try:
        relevance = int(data["relevance"])
        quality = int(data["quality"])
        verdict = str(data["verdict"]).replace("\n", " | ").strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"bad fields: {exc}") from exc
    if not (0 <= relevance <= 10) or not (0 <= quality <= 10):
        raise ValueError("scores outside 0-10")
    if not verdict:
        raise ValueError("empty verdict")
    return relevance, quality, verdict


class OllamaJudge:
    def __init__(self, model: str, base_url: str = OLLAMA_URL,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.model = model
        self.base_url = base_url
        self._transport = transport

    def judge(self, item: Item) -> tuple[int, int, str] | None:
        prompt = render_prompt(item)
        last: Exception | None = None
        for _attempt in range(2):
            try:
                with httpx.Client(transport=self._transport, timeout=120.0) as client:
                    resp = client.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": self.model,
                            "prompt": prompt,
                            "format": "json",
                            "stream": False,
                            "options": {"temperature": 0.2, "num_ctx": 2048},
                        },
                    )
                    resp.raise_for_status()
                    return parse_judgment(resp.json()["response"])
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last = exc
        print(f"judge failed for {item.title!r}: {last}")
        return None

    def unload(self) -> None:
        with httpx.Client(transport=self._transport, timeout=60.0) as client:
            client.post(f"{self.base_url}/api/generate",
                        json={"model": self.model, "keep_alive": 0})


def free_ram_mb() -> int:
    return psutil.virtual_memory().available // (1024 * 1024)


def batch_judge(
    items: list[Item],
    judge: OllamaJudge,
    guard_mb: int = 1500,
    free_ram: Callable[[], int] = free_ram_mb,
) -> tuple[list[tuple[Item, tuple[int, int, str]]], str | None]:
    results: list[tuple[Item, tuple[int, int, str]]] = []
    skipped: str | None = None
    if not items:
        return results, skipped
    try:
        for item in items:
            if free_ram() < guard_mb:
                skipped = "judge unavailable (free RAM below guard)"
                break
            parsed = judge.judge(item)
            if parsed is not None:
                results.append((item, parsed))
        return results, skipped
    finally:
        judge.unload()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_judge.py -v`
Expected: 5 passed (live deselected). Then, with Ollama running: `python -m pytest -m live tests/test_judge.py -v` -> 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/devpulse/judge.py tests/test_judge.py
git commit -m "feat: prompt v3.1 judge with retry, ram guard, unload"
```

---

### Task 7: GitHub collector

**Files:**
- Create: `src/devpulse/collectors/__init__.py`, `src/devpulse/collectors/github.py`, `tests/fixtures/github_rising.json`, `tests/fixtures/github_releases.json`, `tests/test_collectors_github.py`

**Interfaces:**
- Consumes: `Item` (Task 3). Each collector module owns its private `_get` HTTP helper (copy the pattern; do not import helpers across source modules).
- Produces: `collect_rising(min_stars: int = 20, since_days: int = 7, token: str | None = None, transport: httpx.BaseTransport | None = None, today: date | None = None) -> list[Item]` (source `github_rising`); `collect_releases(watchlist: Sequence[str], token: str | None = None, transport: httpx.BaseTransport | None = None, now: datetime | None = None, since_hours: int = 72, per_repo_cap: int = 2) -> list[Item]` (source `github_release`). Both return `[]` on HTTP error and never raise.

- [ ] **Step 1: Create fixture files**

```json
# tests/fixtures/github_rising.json
{
  "items": [
    {
      "full_name": "alice/tiny-linter",
      "html_url": "https://github.com/alice/tiny-linter",
      "stargazers_count": 2571,
      "description": "A tiny linter with unusual depth",
      "language": "Rust"
    },
    {
      "full_name": "bob/vibes",
      "html_url": "https://github.com/bob/vibes",
      "stargazers_count": 88,
      "description": null,
      "language": null
    }
  ]
}
```

```json
# tests/fixtures/github_releases.json
[
  {
    "tag_name": "v0.5.0",
    "html_url": "https://github.com/ollama/ollama/releases/tag/v0.5.0",
    "created_at": "2026-10-03T01:00:00Z",
    "body": "new model support"
  },
  {
    "tag_name": "v0.4.0",
    "html_url": "https://github.com/ollama/ollama/releases/tag/v0.4.0",
    "created_at": "2026-09-20T01:00:00Z",
    "body": "old"
  }
]
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_collectors_github.py
import json
from datetime import date, datetime, timezone
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
        now=datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc),
    )
    assert [i.title for i in items] == ["ollama/ollama v0.5.0"]
    assert items[0].source == "github_release"
    assert "new model support" in items[0].context


def test_releases_empty_watchlist_and_error_path():
    assert collect_releases([], transport=_transport("github_releases.json")) == []
    assert collect_releases(["a/b"],
                            transport=_transport("github_releases.json", 403)) == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_collectors_github.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.collectors'`

- [ ] **Step 4: Implement**

```python
# src/devpulse/collectors/__init__.py
from .devto import collect_articles
from .github import collect_releases, collect_rising
from .hackernews import collect_show_hn, collect_top

DEFAULT_COLLECTORS = [
    collect_rising,
    collect_releases,
    collect_show_hn,
    collect_top,
    collect_articles,
]
```

```python
# src/devpulse/collectors/github.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Sequence

import httpx

from ..models import Item, utcnow_iso

API = "https://api.github.com"


def _get(url: str, params: dict | None, token: str | None,
         transport: httpx.BaseTransport | None) -> dict | list | None:
    headers = {"User-Agent": "devpulse/0.1", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(transport=transport, timeout=20.0, headers=headers) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError):
        return None


def collect_rising(min_stars: int = 20, since_days: int = 7, token: str | None = None,
                   transport: httpx.BaseTransport | None = None,
                   today: date | None = None) -> list[Item]:
    since = (today or date.today()) - timedelta(days=since_days)
    data = _get(
        f"{API}/search/repositories",
        {"q": f"created:>{since.isoformat()} stars:>{min_stars}",
         "sort": "stars", "order": "desc", "per_page": 7},
        token, transport,
    )
    if not isinstance(data, dict):
        return []
    out = []
    for repo in data.get("items", []):
        desc = repo.get("description") or "(no description provided)"
        lang = repo.get("language") or "unknown"
        out.append(Item(
            url=repo.get("html_url", ""),
            title=repo.get("full_name", ""),
            source="github_rising",
            engagement=int(repo.get("stargazers_count") or 0),
            context=f"description: {desc[:200]} | language: {lang}",
            fetched_at=utcnow_iso(),
        ))
    return out


def collect_releases(watchlist: Sequence[str], token: str | None = None,
                     transport: httpx.BaseTransport | None = None,
                     now: datetime | None = None,
                     since_hours: int = 72, per_repo_cap: int = 2) -> list[Item]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=since_hours)
    out: list[Item] = []
    for repo in watchlist:
        data = _get(f"{API}/repos/{repo}/releases", {"per_page": 5}, token, transport)
        if not isinstance(data, list):
            continue
        taken = 0
        for rel in data:
            if taken >= per_repo_cap:
                break
            try:
                created = datetime.fromisoformat(
                    str(rel.get("created_at", "")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if created < cutoff:
                continue
            out.append(Item(
                url=rel.get("html_url", ""),
                title=f"{repo} {rel.get('tag_name', '')}".strip(),
                source="github_release",
                engagement=1,
                context=f"release body: {(rel.get('body') or '(no notes)')[:200]}",
                fetched_at=utcnow_iso(),
            ))
            taken += 1
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_collectors_github.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/devpulse/collectors/ tests/fixtures/github_*.json tests/test_collectors_github.py
git commit -m "feat: github rising search and release collectors"
```

---

### Task 8: Hacker News collector

**Files:**
- Create: `src/devpulse/collectors/hackernews.py`, `tests/fixtures/hn_show.json`, `tests/fixtures/hn_top.json`, `tests/test_collectors_hn.py`

**Interfaces:**
- Produces: `collect_show_hn(limit: int = 8, transport: httpx.BaseTransport | None = None) -> list[Item]`; `collect_top(limit: int = 8, transport: httpx.BaseTransport | None = None) -> list[Item]`. Both source `hackernews`, engagement = points, url falls back to `https://news.ycombinator.com/item?id={objectID}` when no link, context = `link domain: <netloc>`, `[]` on HTTP error.

- [ ] **Step 1: Create fixtures**

```json
# tests/fixtures/hn_show.json
{
  "hits": [
    {"title": "Show HN: A tool I built", "url": "https://example.com/tool",
     "points": 3531, "objectID": "1"},
    {"title": "Show HN: No link", "points": 12, "objectID": "2"}
  ]
}
```

```json
# tests/fixtures/hn_top.json
{
  "hits": [
    {"title": "Top story about Rust", "url": "https://blog.example.org/post",
     "points": 400, "objectID": "9"}
  ]
}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_collectors_hn.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_collectors_hn.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.collectors.hackernews'`

- [ ] **Step 4: Implement**

```python
# src/devpulse/collectors/hackernews.py
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from ..models import Item, utcnow_iso

ALGOLIA = "https://hn.algolia.com/api/v1/search"


def _get(params: dict, transport: httpx.BaseTransport | None) -> dict | None:
    try:
        with httpx.Client(transport=transport, timeout=20.0,
                          headers={"User-Agent": "devpulse/0.1"}) as client:
            resp = client.get(ALGOLIA, params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError):
        return None


def _to_items(data: dict | None) -> list[Item]:
    if not isinstance(data, dict):
        return []
    out = []
    for hit in data.get("hits", []):
        link = hit.get("url") or \
            f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        netloc = urlparse(link).netloc or "(no link)"
        out.append(Item(
            url=link,
            title=hit.get("title") or "",
            source="hackernews",
            engagement=int(hit.get("points") or 0),
            context=f"link domain: {netloc}",
            fetched_at=utcnow_iso(),
        ))
    return out


def collect_show_hn(limit: int = 8, transport: httpx.BaseTransport | None = None) -> list[Item]:
    return _to_items(_get({"tags": "show_hn", "hitsPerPage": limit}, transport))[:limit]


def collect_top(limit: int = 8, transport: httpx.BaseTransport | None = None) -> list[Item]:
    return _to_items(_get({"tags": "front_page", "hitsPerPage": limit}, transport))[:limit]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_collectors_hn.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/devpulse/collectors/hackernews.py tests/fixtures/hn_*.json tests/test_collectors_hn.py
git commit -m "feat: hacker news show and top collectors via algolia"
```

---

### Task 9: dev.to collector

**Files:**
- Create: `src/devpulse/collectors/devto.py`, `tests/fixtures/devto_articles.json`, `tests/test_collectors_devto.py`

**Interfaces:**
- Produces: `collect_articles(limit: int = 8, transport: httpx.BaseTransport | None = None) -> list[Item]` (source `devto`, engagement = `public_reactions_count`, context = `published <date> | <description[:200]>`, `[]` on HTTP error).

- [ ] **Step 1: Create fixture**

```json
# tests/fixtures/devto_articles.json
[
  {"title": "FastAPI caching done right",
   "url": "https://dev.to/author/fastapi-caching-1abc",
   "public_reactions_count": 152,
   "published_at": "2026-10-02",
   "description": "A practical guide to caching in FastAPI apps"},
  {"title": "Short one",
   "url": "https://dev.to/author/short-2def",
   "public_reactions_count": 3,
   "published_at": "2026-10-02",
   "description": null}
]
```

- [ ] **Step 2: Write the failing tests**

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_collectors_devto.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.collectors.devto'`

- [ ] **Step 4: Implement**

```python
# src/devpulse/collectors/devto.py
from __future__ import annotations

import httpx

from ..models import Item, utcnow_iso

API = "https://dev.to/api/articles"


def collect_articles(limit: int = 8, transport: httpx.BaseTransport | None = None) -> list[Item]:
    try:
        with httpx.Client(transport=transport, timeout=20.0,
                          headers={"User-Agent": "devpulse/0.1"}) as client:
            resp = client.get(API, params={"per_page": limit, "top": 1})
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for art in data[:limit]:
        desc = art.get("description") or "(no description)"
        out.append(Item(
            url=art.get("url", ""),
            title=art.get("title", ""),
            source="devto",
            engagement=int(art.get("public_reactions_count") or 0),
            context=f"published {art.get('published_at', '')} | {desc[:200]}",
            fetched_at=utcnow_iso(),
        ))
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_collectors_devto.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/devpulse/collectors/devto.py tests/fixtures/devto_articles.json tests/test_collectors_devto.py
git commit -m "feat: dev.to article collector"
```

---

### Task 10: Pipeline orchestrator

**Files:**
- Create: `src/devpulse/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Item` (3), `Store` (5), `batch_judge` + `OllamaJudge` (6), collector callables (7-9).
- Produces: `DigestStats(scanned: int, judged: int, skipped_reason: str | None, minutes: float)`; `run_pipeline(store: Store, judge_factory: Callable[[], OllamaJudge], collectors: Sequence[Callable[[], list[Item]]] | None = None, token: str | None = None, watchlist: Sequence[str] = (), model: str = "qwen2.5:7b") -> DigestStats`. Flow: run every collector (each in its own try/except; a raising collector is treated as `[]`) -> dedupe by `url_hash` -> set `engagement_pct` within each source group -> `insert_items` -> `items_missing_judgment` -> `batch_judge` -> `save_judgment` for each result -> `record_digest`. `skipped_reason` from the guard wins over the "no new items" reason.

- [ ] **Step 1: Write the failing tests**

```python
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
                         collectors=[exploding, good])
    assert stats.scanned == 1  # duplicates collapsed, explosion ignored
    assert stats.judged == 1
    assert stats.skipped_reason is None
    rows = store.judged_rows()
    assert len(rows) == 1
    assert rows[0][1].quality == 9 and rows[0][1].model == "qwen2.5:7b"
    assert store.last_digest() is not None
    # a second run judges nothing new
    stats2 = run_pipeline(store, judge_factory=FakeJudge, collectors=[good])
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
    )
    pending_after = store.search("")  # unused; read raw instead
    import sqlite3
    conn = store.conn
    pcts = {r["title"]: r["engagement_pct"]
            for r in conn.execute("SELECT title, engagement_pct FROM items")}
    assert pcts["low"] == 0.0     # nothing in its source group is strictly lower
    assert pcts["high"] == 0.5    # exactly one of two github_rising items is lower
    assert pcts["hn only"] == 0.0  # single-item group is neutral-eligible by design
    assert pending_after is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.pipeline'`

- [ ] **Step 3: Implement**

```python
# src/devpulse/pipeline.py
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .collectors.devto import collect_articles
from .collectors.github import collect_releases, collect_rising
from .collectors.hackernews import collect_show_hn, collect_top
from .judge import OllamaJudge, batch_judge
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

    results, skipped = batch_judge(pending, judge_factory())
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
```

Note: `judge_factory` in tests returns the same `FakeJudge` instance each call, matching the single-use pattern of production (fresh `OllamaJudge` per run).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: 3 passed. If `pcts["high"]` assertion is wrong (1 of 2 below 900 -> 0.5 is correct: only engagement 10 < 900), keep 0.5. Fix only the test's misleading comment, not the code.

- [ ] **Step 5: Commit**

```bash
git add src/devpulse/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline with source isolation, diff, percentile, guard"
```

---

### Task 11: Digest composer

**Files:**
- Create: `src/devpulse/composer.py`, `tests/test_composer.py`

**Interfaces:**
- Consumes: `Item`, `Judgment` (3), `is_sleeper_eligible` (4), `DigestStats` (10).
- Produces: `compose_digest(date_str: str, top: list[tuple[Item, Judgment]], sleeper: tuple[Item, Judgment] | None, releases: list[Item], stats: DigestStats, model: str) -> str`. Section order per spec section 9: title, TOP 5 FOR YOU, SLEEPER PICK, NEW RELEASES (omitted when empty), footer `scanned/judged/minutes/model/on-device`. Guard skipped: returns `daily run skipped: <reason>` when `stats.skipped_reason` is set and judgment ran (not the "no new items" case). Message never exceeds 1900 chars: drop lowest-ranked top items first, never the footer or sleeper. Source labels: `github_rising` -> `github`, `devto` -> `dev.to`, others verbatim.

- [ ] **Step 1: Write the failing tests**

```python
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
    assert "42 scanned, 18 judged, 6.4 min, qwen2.5:7b, on-device" in msg
    assert not _EMOJI.search(msg)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_composer.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.composer'`

- [ ] **Step 3: Implement**

```python
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
        if len("\n".join(lines)) + len(body) + len(footer) + 12 <= MAX_MESSAGE:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_composer.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/devpulse/composer.py tests/test_composer.py
git commit -m "feat: digest composer with emoji guard and discord length cap"
```

---

### Task 12: Discord bot (commands, scheduler, entry point)

**Files:**
- Create: `src/devpulse/bot.py`, `src/devpulse/main.py`, `tests/test_bot.py`

**Interfaces:**
- Consumes: `Settings` (2), `Store` (5), `run_pipeline` (10), `compose_digest` (11), `OllamaJudge` (6).
- Produces: `can_refresh(user_id: int, owner_id: int | None) -> bool`; `seconds_until(hhmm: str, now: datetime) -> float` (local machine time, rolls to next day); `cmd_dig(store: Store, topic: str) -> str`; `cmd_sleeper(store: Store, days: int = 7) -> str`; `cmd_releases(store: Store) -> str`; `cmd_status(store: Store) -> str`; `safe_run(run_digest: Callable[[], str]) -> str` (never raises; returns `daily run skipped: <exc>`); `build_bot(settings: Settings, store: Store, run_digest: Callable[[], str]) -> discord.Client` (syncs slash commands on ready, schedules at `settings.digest_time`, sends via `settings.digest_channel_id`); `build_run_digest(settings: Settings, store: Store, collectors=None, judge_factory=None) -> Callable[[], str]` (pipeline + rank top 5 by relevance then quality + sleeper + releases + compose); `main()` loads settings, opens `devpulse.db`, runs the bot.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bot.py
from datetime import datetime, timedelta

from devpulse.bot import (
    build_run_digest, can_refresh, cmd_dig, cmd_releases, cmd_sleeper, cmd_status,
    safe_run, seconds_until,
)
from devpulse.models import Item, Judgment
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
                                 judged_at="2026-10-03T00:01:00+00:00"))


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


def test_safe_run_never_raises():
    def boom():
        raise RuntimeError("ollama down")

    assert safe_run(boom) == "daily run skipped: ollama down"
    assert safe_run(lambda: "ok") == "ok"


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
    )
    msg = run()
    assert "DevPulse Daily -" in msg
    assert "TOP 5 FOR YOU" in msg and "alice/tool" in msg
    assert "on-device" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bot.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'devpulse.bot'`

- [ ] **Step 3: Implement bot.py**

```python
# src/devpulse/bot.py
from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime

import discord
from discord import app_commands

from .composer import compose_digest
from .judge import OllamaJudge
from .models import Item
from .pipeline import run_pipeline
from .settings import Settings
from .store import Store


def can_refresh(user_id: int, owner_id: int | None) -> bool:
    return owner_id is not None and user_id == owner_id


def seconds_until(hhmm: str, now: datetime) -> float:
    hour, minute = (int(part) for part in hhmm.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def safe_run(run_digest: Callable[[], str]) -> str:
    try:
        return run_digest()
    except Exception as exc:
        return f"daily run skipped: {exc}"


def cmd_dig(store: Store, topic: str) -> str:
    rows = store.search(topic)
    if not rows:
        return f"no stored verdicts match {topic!r}"
    lines = [f"results for {topic!r}:"]
    for item, j in rows[:10]:
        lines.append(f"- {item.title} [q {j.quality}] {j.verdict}")
    return "\n".join(lines)


def cmd_sleeper(store: Store, days: int = 7) -> str:
    rows = store.sleepers(days)
    if not rows:
        return f"no sleeper picks in the last {days} days"
    lines = [f"sleeper picks, last {days} days:"]
    for item, j in rows[:5]:
        pct = round(item.engagement_pct * 100)
        lines.append(f"- {item.title} [q {j.quality}, engagement bottom {pct}%] {j.verdict}")
    return "\n".join(lines)


def cmd_releases(store: Store) -> str:
    releases = store.releases()
    if not releases:
        return "no new watchlist releases"
    return "recent releases:\n" + "\n".join(f"- {r.title}" for r in releases)


def cmd_status(store: Store) -> str:
    row = store.last_digest()
    if row is None:
        return "no digest runs yet"
    msg = f"last run: {row[4]}, {row[1]} scanned, {row[2]} judged"
    if row[3]:
        msg += f", skipped: {row[3]}"
    return msg


def build_run_digest(settings: Settings, store: Store,
                     collectors: Sequence[Callable[[], list[Item]]] | None = None,
                     judge_factory: Callable[[], OllamaJudge] | None = None
                     ) -> Callable[[], str]:
    def run() -> str:
        factory = judge_factory or (lambda: OllamaJudge(settings.model))
        stats = run_pipeline(store, judge_factory=factory, collectors=collectors,
                             token=settings.github_token, watchlist=settings.watchlist,
                             model=settings.model)
        ranked = sorted(store.judged_rows(),
                        key=lambda pair: (pair[1].relevance, pair[1].quality),
                        reverse=True)[:5]
        sleepers = store.sleepers()
        return compose_digest(
            date_str=str(datetime.now().date()),
            top=ranked,
            sleeper=sleepers[0] if sleepers else None,
            releases=store.releases(),
            stats=stats,
            model=settings.model,
        )

    return run


def build_bot(settings: Settings, store: Store, run_digest: Callable[[], str]) -> discord.Client:
    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)
    tree = app_commands.CommandTree(bot)

    @tree.command(name="dig", description="Search stored verdicts by topic")
    @app_commands.describe(topic="keyword, e.g. fastapi")
    async def dig_cmd(interaction: discord.Interaction, topic: str) -> None:
        await interaction.response.send_message(cmd_dig(store, topic)[:1999])

    @tree.command(name="sleeper", description="Best sleeper picks from the last 7 days")
    async def sleeper_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(cmd_sleeper(store)[:1999])

    @tree.command(name="releases", description="Recent watchlist releases")
    async def releases_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(cmd_releases(store)[:1999])

    @tree.command(name="status", description="Last digest run and judge health")
    async def status_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(cmd_status(store)[:1999])

    @tree.command(name="refresh", description="Force a digest run now (owner only)")
    async def refresh_cmd(interaction: discord.Interaction) -> None:
        if not can_refresh(interaction.user.id, settings.owner_id):
            await interaction.response.send_message(
                "only the owner can run /refresh", ephemeral=True)
            return
        await interaction.response.send_message("collecting and judging...")
        msg = await asyncio.to_thread(safe_run, run_digest)
        await interaction.followup.send(msg[:1999])

    async def scheduler() -> None:
        while not bot.is_closed():
            await asyncio.sleep(seconds_until(settings.digest_time, datetime.now()))
            msg = await asyncio.to_thread(safe_run, run_digest)
            channel = bot.get_channel(settings.digest_channel_id)
            if channel is not None:
                await channel.send(msg[:1999])

    @bot.event
    async def on_ready() -> None:
        await tree.sync()
        bot.loop.create_task(scheduler())

    return bot
```

- [ ] **Step 4: Implement main.py and the console entry**

```python
# src/devpulse/main.py
from .bot import build_bot, build_run_digest
from .settings import load_settings
from .store import Store


def main() -> None:
    settings = load_settings()
    store = Store("devpulse.db")
    store.init_schema()
    run_digest = build_run_digest(settings, store)
    bot = build_bot(settings, store, run_digest)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
```

Add to `pyproject.toml` under `[project]`:

```toml
[project.scripts]
devpulse = "devpulse.main:main"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot.py -v`
Expected: 5 passed. Then full suite: `python -m pytest -v` -> all green; `ruff check .` -> clean.

- [ ] **Step 6: Commit**

```bash
git add src/devpulse/bot.py src/devpulse/main.py tests/test_bot.py pyproject.toml
git commit -m "feat: discord commands, scheduler, digest entry point"
```

---

### Task 13: README and final verification

**Files:**
- Modify: `README.md`
- Create: none

**Interfaces:**
- Consumes: everything; this task only documents and verifies.

- [ ] **Step 1: Replace README.md with the real one**

```markdown
# devpulse

A Discord bot that gathers what is moving in tech - new releases, rising GitHub
repos, Show HN posts, dev.to articles - and judges every item with an open-weight
model (qwen2.5:7b) running **locally** through Ollama. Each day it posts one
digest: the top 5 items for your stack, one sleeper pick (high quality, low hype,
scored by arithmetic, not vibes), and new releases from your watchlist.

## Why open

Everything runs on-device: collectors call free public APIs, the judge runs on
your own machine, and results live in a local SQLite file. No cloud inference, no
subscription, nothing you fetch leaves the machine.

## Setup

1. Install Python 3.11+ and [Ollama](https://ollama.com); then `ollama pull qwen2.5:7b`
2. Create a Discord application, invite the bot, copy the token
3. `python -m pip install -e ".[dev]"`
4. Copy `.env.example` to `.env` and fill in token, channel id, owner id, watchlist
5. `devpulse` - the digest posts at DIGEST_TIME every day

## Commands

| Command | What it does |
|---|---|
| `/dig <topic>` | search stored verdicts |
| `/sleeper` | top sleeper picks from the last 7 days |
| `/releases` | recent watchlist releases |
| `/status` | last run, counts, judge health |
| `/refresh` | owner-only: run a digest now |

## Development

- `pytest` runs the hermetic suite (no network, no model)
- `pytest -m live` hits real APIs and local Ollama (manual only)
- `ruff check .` - lint

MIT licensed. Built for the Hacktoberfest 2026 Weekend Challenge.
```

- [ ] **Step 2: Full verification pass**

Run: `ruff check .`
Expected: no issues. If issues: fix code, never the linter config.

Run: `python -m pytest -v`
Expected: every test passes, none skipped except `live`.

Run: `python -m pytest -m live tests/test_judge.py -v` (Ollama running)
Expected: 1 passed; afterwards `curl` the unload or just note the guard already unloaded.

- [ ] **Step 3: Manual smoke (not automated - required for the submission video)**

1. Discord Developer Portal -> create app -> Bot -> copy token to `.env`
2. OAuth2 URL generator: scopes `bot applications.commands`, permission Send Messages; invite to your own server
3. Fill `DIGEST_CHANNEL_ID`, `DISCORD_OWNER_ID` (your user id)
4. Run `devpulse`, confirm `/status` answers and `/refresh` works (owner) and is denied for anyone else
5. Run `/refresh` again with Ollama stopped: expect `daily run skipped: ...` - the failure path
6. Screenshot the digest for the DEV post (proof for Demo section)

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: real readme with setup, commands, and development"
```

Push and open the GitHub repo only when the user explicitly asks.

---

## Self-Review

**1. Spec coverage** (spec section -> task): 1 intent/success -> verified manually in 13.3; 2 constraints -> Global Constraints + tasks 4/6/11; 3 architecture -> tasks 6/10/12; 4 collectors -> tasks 7/8/9; 5 normalizer -> task 3; 6 storage -> task 5 (incl. the engagement_pct extension, flagged); 7 judge -> task 6; 8 sleeper formula -> task 4; 9 bot -> tasks 11/12; 10 testing -> every task's TDD + task 1 CI; 11 hygiene -> .gitignore (repo init), task 13 verification, Global Constraints; 12 submission checklist -> task 13.3 + manual item collection after. Gaps: none found.

**2. Placeholder scan:** no TBD/TODO/"similar to Task N"/"fill in"; every code step carries real, runnable code and every test step names its file, command, and expected outcome.

**3. Type consistency:** `judge_factory: Callable[[], OllamaJudge]` matches pipeline/bot/tests; `run_pipeline(...) -> DigestStats` matches composer's input; `Store.sleepers()` returns `list[tuple[Item, Judgment]]` in tasks 5, 11, 12; `batch_judge` results tuple shape `(Item, tuple[int,int,str])` is what pipeline unpacks. Two bugs fixed during review: (a) the pipeline's collector chain originally type-checked collectors against `DEFAULT_COLLECTORS` identity, which silently dropped token/watchlist binding - replaced with `_default_chain(token, watchlist)`; (b) the percentile test's expected values were recomputed from the actual formula (low=0.0, high=0.5). A stray import and a `__import__` hack in Task 12 were also removed rather than left as delete-me instructions.

**4. Review Focus:** each of the five lines has its pinning test: (1) wrong-shape JSON -> `test_parse_coerces_and_validates`; (2) guard boundary -> `test_batch_guard_boundary_sequential_and_unload_once`; (3) 503 isolation -> collector 503 tests + `test_isolates_raising_collector_and_judges_deduped_items`; (4) degenerate percentiles -> `test_percentile_degenerate_groups`; (5) 2000-char overflow -> `test_overflow_drops_top_items_keeps_sleeper_and_footer` (plus `test_full_digest_exact_layout_no_emoji` for the emoji constraint).

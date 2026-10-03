# src/devpulse/store.py
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

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
        now = datetime.now(UTC).isoformat(timespec="seconds")
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
            cutoff = (datetime.now(UTC) - timedelta(days=since_days)).isoformat()
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

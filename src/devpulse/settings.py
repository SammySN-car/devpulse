from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

_ENV_KEYS = (
    "DISCORD_BOT_TOKEN",
    "DIGEST_CHANNEL_ID",
    "DIGEST_TIME",
    "MODEL",
    "WATCHLIST",
    "GITHUB_TOKEN",
    "DISCORD_OWNER_ID",
)


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
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
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

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


def test_digest_time_range_validation(tmp_path):
    env = tmp_path / ".env"
    for bad in ("24:00", "07:60", "99:99", "7:00"):
        env.write_text(
            "DISCORD_BOT_TOKEN=t\nDIGEST_CHANNEL_ID=1\n" f"DIGEST_TIME={bad}\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            load_settings(str(env))
    for good in ("00:00", "07:00", "23:59"):
        env.write_text(
            "DISCORD_BOT_TOKEN=t\nDIGEST_CHANNEL_ID=1\n" f"DIGEST_TIME={good}\n",
            encoding="utf-8",
        )
        assert load_settings(str(env)).digest_time == good


def test_is_frozen():
    s = Settings(discord_token="t", digest_channel_id=1)
    with pytest.raises(FrozenInstanceError):
        s.discord_token = "other"  # type: ignore[misc]

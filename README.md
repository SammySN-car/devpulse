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

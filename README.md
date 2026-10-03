# devpulse

A Discord bot that collects what is moving in the tech world (new releases, rising
GitHub repos, Show HN), judges it with a locally-run open-weight model, and posts a
daily digest with a "sleeper pick" - high quality items that the crowd has not
noticed yet.

**Status:** in design. Built for Hacktoberfest 2026 Weekend Challenge.

## Why open

Runs entirely on-device: collection, local-model judgment (qwen2.5:7b via Ollama),
and storage (SQLite). No cloud inference, no data leaving the machine, no subscription.

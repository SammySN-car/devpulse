# devpulse — Design Specification

Date: 2026-10-03
Status: awaiting user review
Path: architectural (this spec precedes the implementation plan)

## 1. Intent

**Problem.** Keeping up with the tech industry is hard: new tool releases, rising
GitHub repos, company launches, and underrated projects that never get noticed.
Existing solutions are either firehoses (scroll forever) or paid/closed services.

**Product.** A Discord bot that collects fresh tech items from free public sources,
judges them with an open-weight model running locally, and posts a daily digest to
one channel: top items for *this* developer, plus one "sleeper pick" (high quality,
low hype), plus new releases from a watchlist.

**Primary user.** The builder (a Python/FastAPI/web + AI developer). Real friends
with the same annoyance are the second users; they receive the bot in a shared
Discord server and are quoted honestly in the contest write-up.

**Success criteria.**
1. A digest posts daily with verdicts a busy developer would actually read.
2. The sleeper pick provably diverges from engagement (quality computed separately
   from hype).
3. Nothing leaves the machine: collection, judgment (qwen2.5:7b via Ollama), and
   storage (SQLite) are all local.
4. Friends use it after the contest ends.
5. The repo and DEV post meet the Hacktoberfest 2026 Weekend Challenge checklist
   (Section 12).

## 2. Constraints and non-goals

**Constraints.**
- Deadline: submissions due 2026-10-05 06:59 UTC.
- Hardware: 15.6 GB RAM, RTX 2050 (4 GB VRAM), hybrid GPU/CPU inference. Model must
  be unloaded after each batch; a RAM guard aborts any batch below 1500 MB free.
- Sources: free, official, no scraping of ToS-protected sites. Twitter/X excluded
  (paid API). Reddit excluded (unauthenticated 403s reported in 2026).
- Submission claims must be truthful: the post says what actually happened,
  including real handover quotes from real friends.

**Non-goals (YAGNI).**
- No web dashboard, no fine-tuning, no user accounts, no Twitter, no multi-server
  tenancy, no mobile app, no paid APIs.

## 3. Architecture

```
Collectors -> Normalizer -> Diff (SQLite) -> Judge (Ollama, local) -> Scoring
                                                                     -> SQLite
                                                                     -> Compose -> Discord
```

Component rules:
- Each collector is isolated: one source failing never aborts the run.
- The judge runs sequentially (never parallel requests).
- All reads for slash commands come from SQLite; they never load the model.

## 4. Collectors

One module per source in `src/devpulse/collectors/`. Each returns raw items:
`{title, url, source, engagement, context, fetched_at}`.

| Module | Endpoint | Items | Engagement |
|---|---|---|---|
| `github.py` | `api.github.com/repos/{repo}/releases` for WATCHLIST | releases | release recency |
| `github.py` | `api.github.com/search/repositories?q=created:>YYYY-MM-DD stars:>N&sort=stars` | rising repos | stars |
| `hackernews.py` | `hacker-news.firebaseio.com/v0` (top/new) or Algolia `tags=show_hn` | stories | points |
| `devto.py` | `dev.to/api/articles` | articles | public_reactions_count |
| `producthunt.py` (optional tier) | GraphQL v2, free developer token | launches | votes |

Notes:
- GitHub trending has no official API; rising repos are emulated via search with an
  absolute `created:` date (relative `>7d` is rejected with HTTP 422).
- Optional sources (Product Hunt) are enabled only when their token exists in `.env`.
- Collector HTTP layer: User-Agent set, timeout 20 s, errors logged and converted to
  an empty result list.

## 5. Normalizer

- Canonical item shape; URL as identity.
- Dedupe across sources by normalized URL (lowercase, strip tracking params, strip
  trailing slash).
- `engagement_pct` is computed *within the day's batch and source class* (raw stars,
  points, and reactions are not comparable across sources).
- Release items are displayed in their own section and are never sleeper
  candidates; only content items (GitHub rising, HN, dev.to) participate in
  sleeper scoring.

## 6. Diff and storage (SQLite)

Schema (single file `devpulse.db`, git-ignored):

```sql
items (
  url_hash TEXT PRIMARY KEY,   -- sha256 of normalized url
  url TEXT, title TEXT, source TEXT,
  engagement INTEGER,
  engagement_pct REAL, context TEXT,
  fetched_at TEXT
);
judgments (
  url_hash TEXT PRIMARY KEY REFERENCES items(url_hash),
  relevance INTEGER, quality INTEGER, verdict TEXT,
  model TEXT, prompt_version TEXT,      -- enables deliberate re-judging later
  status TEXT,                          -- always 'ok' today; reserved (see §7 erratum)
  judged_at TEXT
);
digests (
  id INTEGER PRIMARY KEY, posted_at TEXT,
  item_count INTEGER, judged_count INTEGER, skipped_reason TEXT
);
```

- `INSERT OR IGNORE` semantics: an item with a judgment is never judged twice.
- Changing `MODEL` or `prompt_version` does not auto-invalidate old rows; re-judging
  is an explicit future operation.

## 7. Judge

- Model: `qwen2.5:7b` through local Ollama (`localhost:11434`), JSON mode,
  `temperature 0.2`, context window capped at 2048 tokens.
- Prompt ("v3 final") contents:
  - persona: one developer (Python/FastAPI/web + AI tools)
  - item block: title, source, engagement, context (link domain / description)
  - relevance anchors: 0-2 unrelated, 3-4 tangential, 5-6 worth a glance,
    7-8 directly useful this month, 9-10 changes how they work
  - quality anchors: 0-2 junk/abandoned/misleading, 3-4 shallow demo,
    5-6 solid but ordinary, 7-8 crafted/novel/unusually deep, 9-10 landmark
  - scoring-logic illustrations only (reasoning, never copyable verdict text)
  - rules: use only provided text (no invented features); always respond in
    English; verdict is exactly two short lines (what it is; worth clicking yes/no)
  - output: `{"relevance": int, "quality": int, "verdict": str}`
- Handling: one item per request; parse failure -> one retry -> logged, item left
  unjudged (no row) and retried on the next run; per-attempt failures surface as a
  scanned/judged gap in the digest footer, and an all-fail run surfaces as a skip
  message.
  [erratum 2026-10-04] Failed items stay pending (LEFT JOIN NULL) instead of
  writing a terminal `status='unjudged'` row, so retry is automatic and no
  explicit re-judging operation is needed to recover; the `status` column stays
  reserved for future deliberate re-judging.
- Runtime budget: 15-40 items/day, sequential, 5-10 minutes; model receives
  `keep_alive: 0` immediately after the batch so RAM is reclaimed.

### Spike evidence (2026-10-03, `spikes/prototype_judge.py`)

| Signal | llama3.2 (3B) | qwen2.5:7b |
|---|---|---|
| Score spread | rel=8/qual=8 on 10 of 15 items | rel 5-9, quality 3-8 |
| Example-echo leakage | 6 of 15 verdicts | none |
| Parse failures | 0 (v3) | 0 |
| Verdicts | generic or title-echo | evaluative with yes/no |

Decisions proven by the spike: qwen2.5:7b is the model; prompt v3 is the prompt;
English-only rule added; RAM guard and post-batch unload added after free RAM fell
to 1.7 GB during the validation run.

## 8. Sleeper scoring (deterministic, in code)

```
sleeper_score = quality * (1 - engagement_pct)
eligible      = quality >= 7 AND engagement_pct <= 0.40
```

- The model never decides who is a sleeper; it only reports quality. Hype is
  measured, divergence is arithmetic. This is unit-tested as a pure function.

## 9. Discord bot

Stack: `discord.py`; config from `.env` (token, channel id, `DIGEST_TIME`, `MODEL`,
`WATCHLIST`, optional `GITHUB_TOKEN`). Posts only to the configured channel.

Daily digest message (plain text sections):

```
DevPulse Daily - <date>
------------------------------
TOP 5 FOR YOU
1. <repo-or-title> [<source>, <engagement>]
   rel <n> | q <n>
   "<verdict line 1> <verdict line 2>"

SLEEPER PICK
<item> ... quality <n>, engagement bottom <p>% of its source class
"<verdict>"

NEW RELEASES
- <repo> vX.Y <release-url>     (section omitted when empty)

------------------------------
<n> scanned, <n> judged, <n> min, qwen2.5:7b, on-device
```

[erratum 2026-10-05] Release lines render as title + bare release URL; inline
notes text was dropped from the digest (one click plus Discord's link preview
replace them) so the TOP 5 keeps its budget inside Discord's 2000-char message
cap; the release body remains stored and searchable in SQLite.

Slash commands (all SQLite reads unless noted):
- `/dig <topic>` - keyword search over stored verdicts
- `/sleeper` - top eligible sleepers from the last 7 days
- `/releases` - recent watchlist releases
- `/status` - last run, counts, model, judge health
- `/refresh` - owner only; forces a collect->judge cycle now (RAM guard applies)

Scheduler: asyncio loop inside the bot process, fires at `DIGEST_TIME`.

Failure paths (never silent, never crash):
- RAM guard trip or Ollama unreachable -> channel message
  `daily run skipped: judge unavailable`.
- All sources fail -> skip message with counts.
- Zero new items -> post `no new items worth your time today` (count line only).

## 10. Testing strategy

- **Pure logic (default, no network/model):** sleeper formula and gate (TDD first),
  normalizer dedupe and engagement percentile, judge JSON parsing incl. malformed
  retry, digest composer output (an exact-layout pinning test).
- **Collectors:** parse fixture files of real captured API payloads; never live.
- **Bot/DB:** in-memory SQLite; command queries return seeded rows; `/refresh`
  denied for non-owner; failure path posts the skip message with the judge mocked.
- **Live (`-m live`, excluded from CI):** 2-item real fetch + real judgment, run
  manually before submission.
- CI: GitHub Actions, `ruff check` + `pytest -m "not live"`, Ubuntu + Windows
  matrix.

## 11. Repository hygiene

- `.env.example` only; never commit `.env`, `*.db`, logs, or output dumps.
- No nested duplicate project folders.
- `spikes/` is explicitly throwaway; product code lives in `src/devpulse/`.
- Judges read this repo: README, commit messages, and file layout are part of the
  submission.

## 12. Submission checklist (DEV post, due 2026-10-05 06:59 UTC)

- [ ] Working Discord bot with local judge and a real daily digest
- [ ] Public GitHub repo, clean (Section 11)
- [ ] Video/GIF demo of the digest in a real Discord channel
- [ ] One true handover quote from a real friend
- [ ] DEV post sections: What I Built / Demo / Code / How I Built It /
      Why Open Innovation Matters (tags auto-added by the template)
- [ ] Optional: DevRelay agent-session embed; partner category (only if honestly
      applicable)

## 13. Open questions

None blocking. Deferred decisions for the implementation plan: exact digest
composer text layout, watchlist contents (initial list comes from the builder's
own repos of interest), and whether `/dig` triggers a small collect round when a
topic has no stored items (default: no - reads only).


# src/devpulse/judge.py
from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import psutil

from .models import Item

PROMPT_VERSION = "v3.1"
OLLAMA_URL = "http://localhost:11434"

PROMPT_TEMPLATE = """You curate a daily digest for ONE developer: a Python/FastAPI/web dev who \
also builds AI tools.
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
- A polished niche CLI, 40 stars, active commits, MIT -> relevance 8 (fits stack), quality 8 \
(real utility, low hype).
- A viral joke post, 3500 upvotes, no real artifact -> relevance 2, quality 3 (hype >> substance).
- Missing or ambiguous description -> do not guess features; verdict states what is missing.

OUTPUT (JSON only, verdict in exactly 2 short lines)
ALWAYS respond in English, even if the title is not.
{{"relevance": <int>, "quality": <int>, "verdict": "<line 1: what it ACTUALLY is/does, \
based only on provided text; line 2: worth clicking yes/no for this dev and why in a few words>"}}
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

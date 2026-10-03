"""SPIKE v3 (throwaway): prompt-lever test, iteration 2.
Changes vs v2: examples give scoring LOGIC only (no copyable verdict sentences),
explicit "never copy example wording" rule, raw-response logging on parse failure.
Same model (llama3.2), same queries.
"""
import json
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HN_URL = "https://hn.algolia.com/api/v1/search?tags=show_hn&hitsPerPage=8&numericFilters=points%3E5"
GH_URL = "https://api.github.com/search/repositories?q=created:%3E2026-09-26+stars:%3E20&sort=stars&order=desc&per_page=7"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

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
{{"relevance": <int>, "quality": <int>, "verdict": "<line 1: what it ACTUALLY is/does, based only on provided text; line 2: worth clicking yes/no for this dev and why in a few words>"}}
"""


import ctypes

class _Mem(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

def free_ram_mb() -> int:
    m = _Mem(); m.dwLength = ctypes.sizeof(_Mem())
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys // (1024 * 1024)
def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "devpulse-spike/0.3",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def domain_of(url: str | None) -> str:
    if not url:
        return "(no link)"
    return urllib.parse.urlparse(url).netloc


def collect() -> list[dict]:
    items = []
    for hit in fetch(HN_URL)["hits"]:
        items.append({
            "source": "hackernews",
            "title": hit.get("title") or "",
            "engagement": hit.get("points") or 0,
            "context": f"link domain: {domain_of(hit.get('url'))}",
        })
    for repo in fetch(GH_URL)["items"]:
        desc = repo.get("description") or "(no description provided)"
        lang = repo.get("language") or "unknown"
        items.append({
            "source": "github",
            "title": repo["full_name"],
            "engagement": repo.get("stargazers_count") or 0,
            "context": f"description: {desc[:200]} | language: {lang}",
        })
    return items


def judge(item: dict) -> dict:
    prompt = PROMPT_TEMPLATE.format(**item)
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.2},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = json.load(resp)["response"]
    try:
        out = json.loads(raw)
        if not isinstance(out, dict) or "relevance" not in out:
            raise ValueError("missing keys")
        return {
            "relevance": out.get("relevance"),
            "quality": out.get("quality"),
            "verdict": str(out.get("verdict", "")).replace("\n", " | "),
        }
    except (json.JSONDecodeError, ValueError, AttributeError) as exc:
        print(f"     [!] parse failure ({exc}); raw response: {raw[:200]!r}")
        return {"relevance": "?", "quality": "?", "verdict": "(parse failure - see raw above)"}


def main() -> None:
    items = collect()
    print(f"Collected {len(items)} live items. Judging with {MODEL} (prompt v3 + qwen2.5:7b)...\n")
    for i, item in enumerate(items, 1):
        if free_ram_mb() < 1500:
            print("     [!] ABORT: free RAM below 1500 MB - stopping before risking the system")
            break
        v = judge(item)
        print(f'[{i:02d}] {item["source"]:11} | eng={item["engagement"]:>5} '
              f'| rel={v["relevance"]} q={v["quality"]}')
        print(f'     {item["title"][:95]}')
        print(f'     -> {v["verdict"][:170]}\n')
    print("v3 checklist: no example-echo, no parse failures, specific verdicts?")


if __name__ == "__main__":
    main()


# tests/test_judge.py
import json

import httpx
import pytest

from devpulse.judge import PROMPT_VERSION, OllamaJudge, batch_judge, parse_judgment, render_prompt
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


def _judge_returning(
    bodies: list[str], payloads: list[dict] | None = None
) -> tuple[OllamaJudge, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        payload = json.loads(request.content)
        if payloads is not None:
            payloads.append(payload)
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


def test_unload_sends_keep_alive_zero():
    payloads: list[dict] = []
    judge, _calls = _judge_returning([], payloads)
    judge.unload()
    assert payloads == [{"model": "qwen2.5:7b", "keep_alive": 0}]


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


def test_batch_all_fail_returns_unavailable_skip():
    class AllFailJudge:
        def judge(self, item):
            return None

        def unload(self):
            pass

    results, skipped = batch_judge([_item("a"), _item("b")], AllFailJudge(),
                                   free_ram=lambda: 9999)
    assert results == []
    assert skipped == "judge unavailable (2 items failed)"


def test_batch_unload_failure_does_not_escape():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    judge = OllamaJudge(model="qwen2.5:7b", transport=httpx.MockTransport(handler))
    results, skipped = batch_judge([_item("a"), _item("b")], judge,
                                   free_ram=lambda: 9999)
    assert results == []
    assert skipped == "judge unavailable (2 items failed)"


def test_batch_partial_failure_keeps_skipped_none():
    class PartialJudge:
        def __init__(self):
            self.calls = 0

        def judge(self, item):
            self.calls += 1
            return (8, 8, "v") if self.calls == 1 else None

        def unload(self):
            pass

    results, skipped = batch_judge([_item("a"), _item("b"), _item("c")],
                                   PartialJudge(), free_ram=lambda: 9999)
    assert len(results) == 1
    assert skipped is None


@pytest.mark.live
def test_live_judgment_round_trip():
    judge = OllamaJudge(model="qwen2.5:7b")
    rel, qual, verdict = judge.judge(
        _item(title="psf/requests", context="description: Python HTTP library | language: Python")
    )
    judge.unload()
    assert 0 <= rel <= 10 and 0 <= qual <= 10
    assert isinstance(verdict, str) and verdict

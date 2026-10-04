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

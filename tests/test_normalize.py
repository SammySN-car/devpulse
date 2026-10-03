# tests/test_normalize.py
from devpulse.models import Item
from devpulse.normalize import engagement_percentile, normalize_url, url_hash


def test_strips_tracking_params_and_normalizes():
    a = normalize_url("HTTPS://Example.COM/path/?utm_source=x&keep=1&fbclid=zzz")
    assert a == "https://example.com/path?keep=1"


def test_trailing_slash_removed_and_hash_stable_across_variants():
    v1 = "https://example.com/post/"
    v2 = "https://example.com/post?utm_campaign=tw"
    assert normalize_url(v1) == normalize_url(v2)
    assert url_hash(v1) == url_hash(v2)
    assert len(url_hash(v1)) == 64


def test_percentile_counts_strictly_lower():
    assert engagement_percentile(25, [10, 20, 30]) == 2 / 3
    assert engagement_percentile(0, [10, 20]) == 0.0


def test_percentile_degenerate_groups():
    assert engagement_percentile(5, [5]) == 0.0
    assert engagement_percentile(10, [10, 10]) == 0.0
    assert engagement_percentile(99, []) == 0.0


def test_item_defaults():
    it = Item(url="u", title="t", source="devto", engagement=1, context="c", fetched_at="now")
    assert it.engagement_pct == 0.0

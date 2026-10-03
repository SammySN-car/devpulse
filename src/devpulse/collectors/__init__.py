# src/devpulse/collectors/__init__.py
from .devto import collect_articles
from .github import collect_releases, collect_rising
from .hackernews import collect_show_hn, collect_top

DEFAULT_COLLECTORS = [
    collect_rising,
    collect_releases,
    collect_show_hn,
    collect_top,
    collect_articles,
]

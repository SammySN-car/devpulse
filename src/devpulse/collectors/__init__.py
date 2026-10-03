# src/devpulse/collectors/__init__.py
from .github import collect_releases, collect_rising

DEFAULT_COLLECTORS = [
    collect_rising,
    collect_releases,
]

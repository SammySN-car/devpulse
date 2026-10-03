from .github import collect_releases, collect_rising

DEFAULT_COLLECTORS = [
    collect_rising,
    collect_releases,
]

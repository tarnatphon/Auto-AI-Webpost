"""Publisher registry."""
from __future__ import annotations

from typing import Dict, List

from .base import Publisher
from .blogger import BloggerPublisher
from .devto import DevToPublisher
from .github_pages import GitHubPagesPublisher
from .hashnode import HashnodePublisher
from .mastodon import MastodonPublisher
from .medium import MediumManualPublisher
from .telegraph import TelegraphPublisher
from .tumblr import TumblrPublisher
from .wordpress import WordPressPublisher
from .writeas import WriteAsPublisher

PUBLISHERS: Dict[str, Publisher] = {
    p.slug: p for p in [
        DevToPublisher(),
        TelegraphPublisher(),
        WordPressPublisher(),
        GitHubPagesPublisher(),
        BloggerPublisher(),
        TumblrPublisher(),
        MastodonPublisher(),
        WriteAsPublisher(),
        HashnodePublisher(),
        MediumManualPublisher(),
    ]
}


def get(name: str) -> Publisher:
    key = name.strip().lower()
    if key not in PUBLISHERS:
        raise KeyError(f"Unknown publisher '{name}'. Available: {', '.join(PUBLISHERS)}")
    return PUBLISHERS[key]


def get_many(names: str | List[str]) -> List[Publisher]:
    if isinstance(names, str):
        names = [n for n in names.split(",") if n.strip()]
    return [get(n) for n in names]

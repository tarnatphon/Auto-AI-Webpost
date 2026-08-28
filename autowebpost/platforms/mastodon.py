"""Mastodon publisher - free, open social web, links from high-DA instances.

Create a token: your instance -> Preferences -> Development -> New Application
-> scope write:statuses, write:media.
    MASTODON_INSTANCE=https://mastodon.social
    MASTODON_TOKEN=...
"""
from __future__ import annotations

import re

import requests

from ..config import get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher


def _split(text: str, limit: int = 480) -> list:
    parts, buf = [], ""
    for para in text.split("\n\n"):
        cand = (buf + "\n\n" + para).strip() if buf else para
        if len(cand) <= limit:
            buf = cand
        else:
            if buf:
                parts.append(buf)
            for chunk in re.findall(rf".{{1,{limit}}}(?:\s|$)", para, re.S):
                parts.append(chunk.strip())
            buf = ""
    if buf:
        parts.append(buf)
    return parts


class MastodonPublisher(Publisher):
    slug = "mastodon"
    name = "Mastodon"
    env_keys = ["MASTODON_INSTANCE", "MASTODON_TOKEN"]
    docs = "https://docs.joinmastodon.org/methods/statuses/"

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        # Social snippet, not the whole article: hook + link (best practice)
        hook = draft.meta_description[:200]
        link = draft.canonical_url or (draft.images[0].url if draft.images else "")
        text = f"{draft.title}\n\n{hook}" + (f"\n\n{link}" if link else "")
        return {"status": text[:495], "visibility": "public", "language": draft.language}

    def _publish_live(self, draft, persona, payload, **kw) -> PostResult:
        inst = get_secret("MASTODON_INSTANCE").rstrip("/")
        headers = {"Authorization": f"Bearer {get_secret('MASTODON_TOKEN')}", **UA}
        media_ids = []
        img = draft.images[0] if draft.images else None
        if img and img.path and not img.url:
            try:
                with open(img.path, "rb") as fh:
                    up = requests.post(f"{inst}/api/v2/media", headers=headers,
                                       files={"file": fh}, timeout=120)
                up.raise_for_status()
                media_ids = [up.json()["id"]]
            except Exception:
                media_ids = []
        if media_ids:
            payload["media_ids"] = media_ids
        r = requests.post(f"{inst}/api/v1/statuses", headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return PostResult(self.slug, True, url=data.get("url", ""), detail="toot posted")

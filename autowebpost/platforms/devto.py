"""dev.to publisher - free REST API with an api-key. DA ~82, huge dev audience.

API key: https://dev.to/settings/extensions  ->  DEVTO_API_KEY
"""
from __future__ import annotations

import requests

from ..config import get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher
from .htmlutil import markdown_to_html  # used for image URL extraction only


class DevToPublisher(Publisher):
    slug = "devto"
    name = "DEV.to"
    env_keys = ["DEVTO_API_KEY"]
    docs = "https://developers.forem.com/api/v1#tag/articles/operation/createArticle"

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        return {
            "article": {
                "title": draft.title[:99],
                "body_markdown": draft.body_markdown,
                "published": False,          # created as draft; you press publish after review
                "tags": [t for t in draft.tags if t][:4],
                "main_image": (draft.images[0].url if draft.images and draft.images[0].url else ""),
                "canonical_url": draft.canonical_url or None,
                "description": draft.meta_description[:138],
            }
        }

    def _publish_live(self, draft, persona, payload, **kw) -> PostResult:
        r = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": get_secret("DEVTO_API_KEY"), **UA},
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return PostResult(self.slug, True, url=data.get("url", ""), detail="created as DRAFT - review then publish on dev.to")

"""WordPress publisher (self-hosted WP + WordPress.com sites).

Free via Application Passwords (self-hosted) or WP.com app passwords:
  WP_SITE=https://yourblog.com  WP_USER=admin  WP_APP_PASSWORD="xxxx xxxx xxxx"
"""
from __future__ import annotations

import base64

import requests

from ..config import get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher
from .htmlutil import markdown_to_html


class WordPressPublisher(Publisher):
    slug = "wordpress"
    name = "WordPress"
    env_keys = ["WP_SITE", "WP_USER", "WP_APP_PASSWORD"]
    docs = "https://developer.wordpress.org/rest-api/reference/posts/#create-a-post"

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        html = markdown_to_html(draft.body_markdown)
        if draft.images and draft.images[0].path and not draft.images[0].url:
            html = f"<!-- hero image: upload {draft.images[0].path} and set as featured image -->\n" + html
        return {
            "title": draft.title,
            "content": html,
            "status": "draft",   # review in wp-admin, then publish
            "slug": draft.slug,
            "excerpt": draft.meta_description,
            "meta": {
                "description": draft.meta_description,
                "canonical_url": draft.canonical_url or "",
            },
            "tags": draft.tags,
        }

    def _publish_live(self, draft, persona, payload, **kw) -> PostResult:
        site = get_secret("WP_SITE").rstrip("/")
        auth = base64.b64encode(f"{get_secret('WP_USER')}:{get_secret('WP_APP_PASSWORD')}".encode()).decode()
        r = requests.post(
            f"{site}/wp-json/wp/v2/posts",
            headers={"Authorization": f"Basic {auth}", **UA},
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        link = data.get("link", "")
        return PostResult(self.slug, True, url=link, detail=f"created as DRAFT (id {data.get('id')}) - review in wp-admin")

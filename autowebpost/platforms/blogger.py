"""Google Blogger publisher - free, DA ~96, DoFollow links.

Blogger API v3 needs an OAuth2 access token with the blogger scope.
Easiest free path: https://developers.google.com/oauthplayground
  -> authorize https://www.googleapis.com/auth/blogger
  -> exchange code for tokens -> set BLOGGER_ACCESS_TOKEN (+ BLOGGER_REFRESH_TOKEN)
BLOG_ID: from your blog's URL or GET https://www.googleapis.com/blogger/v3/users/self/blogs
"""
from __future__ import annotations

import requests

from ..config import get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher
from .htmlutil import markdown_to_html


class BloggerPublisher(Publisher):
    slug = "blogger"
    name = "Blogger"
    env_keys = ["BLOGGER_ACCESS_TOKEN", "BLOGGER_BLOG_ID"]
    docs = "https://developers.google.com/blogger/docs/3.0/reference/posts/insert"

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        return {
            "kind": "blogger#post",
            "title": draft.title,
            "content": markdown_to_html(draft.body_markdown),
            "labels": draft.tags[:10],
        }

    def _publish_live(self, draft, persona, payload, as_draft: bool = True, **kw) -> PostResult:
        blog_id = get_secret("BLOGGER_BLOG_ID")
        url = f"https://blogger.googleapis.com/v3/blogs/{blog_id}/posts/"
        if as_draft:
            url += "?isDraft=true"
        r = requests.post(url, headers={"Authorization": f"Bearer {get_secret('BLOGGER_ACCESS_TOKEN')}", **UA},
                          json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        detail = "created as DRAFT" if as_draft else "published"
        return PostResult(self.slug, True, url=data.get("url", ""), detail=detail + f" (id {data.get('id')})")

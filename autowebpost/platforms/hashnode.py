"""Hashnode publisher - GraphQL API at gql.hashnode.com (DA ~84, DoFollow).

IMPORTANT (2026): Hashnode's GraphQL API now requires a Hashnode Pro
subscription ($5/mo) - it left the free tier in May 2026. The adapter stays
here because it is excellent for dev niches; flag cost before use.

    HASHNODE_TOKEN=...         (hashnode.com/settings/developer)
    HASHNODE_PUBLICATION_ID=...
"""
from __future__ import annotations

import requests

from ..config import get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher

MUTATION = """
mutation PublishPost($input: PublishPostInput!) {
  publishPost(input: $input) {
    post { id title slug url }
  }
}
"""


class HashnodePublisher(Publisher):
    slug = "hashnode"
    name = "Hashnode"
    env_keys = ["HASHNODE_TOKEN", "HASHNODE_PUBLICATION_ID"]
    docs = "https://gql.hashnode.com"

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        return {
            "query": MUTATION,
            "variables": {
                "input": {
                    "publicationId": get_secret("HASHNODE_PUBLICATION_ID") or "<HASHNODE_PUBLICATION_ID>",
                    "title": draft.title,
                    "contentMarkdown": draft.body_markdown,
                    "tags": [{"slug": t, "name": t} for t in draft.tags[:4]],
                    "originalArticleURL": draft.canonical_url or None,
                }
            },
        }

    def _publish_live(self, draft, persona, payload, as_draft: bool = True, **kw) -> PostResult:
        if as_draft:
            payload["variables"]["input"]["settings"] = {"isDraft": True}
        r = requests.post("https://gql.hashnode.com",
                          headers={"Authorization": get_secret("HASHNODE_TOKEN"), **UA},
                          json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            return PostResult(self.slug, False, detail=str(data["errors"])[:300])
        post = data["data"]["publishPost"]["post"]
        return PostResult(self.slug, True, url=post.get("url", ""), detail=f"draft created (slug {post.get('slug')}) - NOTE: API needs Hashnode Pro")

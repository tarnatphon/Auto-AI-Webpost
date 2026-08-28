"""Medium - NO public API anymore (tokens deprecated, confirmed 2026).

This is a *manual-assist* adapter: it prepares everything Medium's
"Import story" flow needs, so the human step takes 60 seconds.
"""
from __future__ import annotations

from ..models import ArticleDraft, Persona, PostResult
from .base import Publisher


class MediumManualPublisher(Publisher):
    slug = "medium"
    name = "Medium (manual import)"
    env_keys = []
    docs = "https://medium.com/me/stories"

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        return {
            "step 1": "Your canonical/origin URL (required):",
            "url": draft.canonical_url or "<set canonical_url after publishing to your origin site>",
            "step 2": "medium.com -> your profile -> Stories -> Import a story -> paste URL",
            "step 3": "Medium imports content AND sets canonical automatically",
            "warning": "Cross-posting without canonical = duplicate content. Always import, never copy-paste.",
        }

    def _publish_live(self, draft, persona, payload, **kw) -> PostResult:
        return PostResult(self.slug, True, url=draft.canonical_url,
                          detail="MANUAL step ready: medium.com/me/stories -> 'Import a story' -> paste your origin URL")

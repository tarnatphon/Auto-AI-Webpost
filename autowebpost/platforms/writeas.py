"""Write.as publisher - free, minimalist blogging platform (DA ~75, DoFollow).

Write.as allows anonymous posts via its API (no account needed!) and
registered-user posts via login. WriteFreely instances work the same way
(set WRITEAS_INSTANCE to your instance URL).
    WRITEAS_INSTANCE=   (default https://write.as, optional)
    WRITEAS_ALIAS=      (optional - your username)
    WRITEAS_PASSWORD=   (optional - collects a token)
"""
from __future__ import annotations

import requests

from ..config import get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher


class WriteAsPublisher(Publisher):
    slug = "writeas"
    name = "Write.as"
    env_keys = []  # anonymous posting works out of the box
    docs = "https://developers.write.as/docs/api/"

    def _instance(self) -> str:
        return (get_secret("WRITEAS_INSTANCE") or "https://write.as").rstrip("/")

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        return {
            "title": draft.title,
            "body": draft.body_markdown,
            "font": "norm",
            "lang": draft.language,
        }

    def _publish_live(self, draft, persona, payload, **kw) -> PostResult:
        headers = dict(UA)
        alias, password = get_secret("WRITEAS_ALIAS"), get_secret("WRITEAS_PASSWORD")
        if alias and password:
            r = requests.post(f"{self._instance()}/api/auth/login",
                              json={"alias": alias, "pass": password}, headers=UA, timeout=30)
            r.raise_for_status()
            headers["Authorization"] = f"Token {r.json()['data']['access_token']}"
        r = requests.post(f"{self._instance()}/api/posts", json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json().get("data", {})
        url = f"{self._instance()}/{data.get('slug', '')}"
        tok_note = " (SAVE the post token in your vault if anonymous!)" if "token" in data else ""
        return PostResult(self.slug, True, url=url, detail=f"posted{tok_note}")

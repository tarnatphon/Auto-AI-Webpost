"""GitHub Pages origin publisher - FREE, DA ~96, DoFollow, you own the URL.

This is the keystone "origin" strategy: publish the canonical article to your
GitHub-Pages-backed site (Jekyll _posts), then syndicate everywhere else with
canonical_url pointing here. GitHub's Contents API commits the file for you.

    GITHUB_TOKEN=ghp_...        (repo Contents: read/write permission)
    GITHUB_REPO=user/user.github.io
"""
from __future__ import annotations

import base64
import re
from datetime import datetime

import requests

from ..config import get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher


class GitHubPagesPublisher(Publisher):
    slug = "githubpages"
    name = "GitHub Pages (origin site)"
    env_keys = ["GITHUB_TOKEN", "GITHUB_REPO"]
    docs = "https://docs.github.com/en/rest/repos/contents"

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        path = f"_posts/{datetime.utcnow().date()}-{draft.slug}.md"
        content = draft.to_markdown()
        return {
            "message": f"post: {draft.title}",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": "main",
            "path": path,
        }

    def _publish_live(self, draft, persona, payload, **kw) -> PostResult:
        repo = get_secret("GITHUB_REPO")
        path = payload.pop("path")
        api = f"https://api.github.com/repos/{repo}/contents/{path}"
        # don't overwrite existing
        exists = requests.get(api, headers={"Authorization": f"Bearer {get_secret('GITHUB_TOKEN')}", **UA}, timeout=30)
        if exists.status_code == 200:
            payload["sha"] = exists.json()["sha"]
        r = requests.put(api, headers={"Authorization": f"Bearer {get_secret('GITHUB_TOKEN')}", **UA},
                         json=payload, timeout=60)
        r.raise_for_status()
        user = repo.split("/")[0]
        # standard user pages URL (works for <user>.github.io repos)
        site = repo.rsplit("/", 1)[1].replace(".github.io", "")
        url = f"https://{user}.github.io/" + ("" if site == user else f"{site}/") + path.replace("_posts/", "")[:-3] + ".html"
        return PostResult(self.slug, True, url=url, detail=f"committed {path} - Jekyll will build in ~1 min")

"""Reddit publisher - high-authority link source, official OAuth2 API.

Reddit is a *public, undraftable* platform: every API submission is immediately
live in the target subreddit. This project keeps that honest - the adapter is
registered, but it is never in the default syndication list, and the `smoke`
command refuses to hit it live without `--force`.

Setup:
    REDDIT_CLIENT_ID       (script app at https://www.reddit.com/prefs/apps)
    REDDIT_CLIENT_SECRET
    REDDIT_USERNAME        (your account)
    REDDIT_PASSWORD        (your account password)
    REDDIT_SUBREDDIT       (e.g. automation - no /r/ prefix)

Best practice (see docs/03-compliance.md): post value, not links-only; read the
subreddit rules; one sub, one account, no cross-spam.
"""
from __future__ import annotations

import requests

from ..config import get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher

AUTH_URL = "https://www.reddit.com/api/v1/access_token"
SUBMIT_URL = "https://oauth.reddit.com/api/submit"
TOKEN_FILE_HINT = "set REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD in .env"


class RedditPublisher(Publisher):
    slug = "reddit"
    name = "Reddit"
    env_keys = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"]
    docs = "https://www.reddit.com/dev/api/#POST_api_submit"
    # No draft mode - every API submit is public immediately. The base publisher
    # refuses live unless the caller opts in with allow_public / AUTOWEBPOST_ALLOW_PUBLIC.
    public_live = True

    def __init__(self) -> None:
        self._token: str = ""

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        sub = (get_secret("REDDIT_SUBREDDIT") or "").strip().lstrip("r/")
        title = draft.title[:300]
        body = draft.body_markdown
        url = draft.canonical_url or ""
        # Want your link to get seen? Provide something for the readers in the
        # body and link the source; Reddit's own rules dislike link-dumps.
        return {
            "sr": sub or "test",
            "title": title,
            "kind": "link" if url else "self",
            "url": url,
            "text": body,
            "resubmit": False,
            "sendreplies": True,
        }

    def _token_live(self) -> str:
        if self._token:
            return self._token
        r = requests.post(AUTH_URL,
                          auth=(get_secret("REDDIT_CLIENT_ID"), get_secret("REDDIT_CLIENT_SECRET")),
                          data={"grant_type": "password",
                                "username": get_secret("REDDIT_USERNAME"),
                                "password": get_secret("REDDIT_PASSWORD")},
                          headers={"User-Agent": "AutoAIWebPost/0.1 (+https://github.com/tarnatphon/Auto-AI-Webpost)"},
                          timeout=30)
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    def _publish_live(self, draft, persona, payload, **kw) -> PostResult:
        headers = {**UA, "Authorization": f"bearer {self._token_live()}"}
        # Reddit's submit endpoint expects form-encoded fields.
        data = {k: (v if v is not None else "") for k, v in payload.items()}
        r = requests.post(SUBMIT_URL, headers=headers, data=data, timeout=60)
        if r.status_code in (400, 401, 403):
            # Raise so Base.publish reports the API body as a normal HTTP error.
            r.raise_for_status()
        r.raise_for_status()
        parsed = r.json()
        j = parsed.get("json", parsed)
        if not j.get("success"):
            errs = "; ".join(" ".join(str(x) for x in e) for e in j.get("errors", []))
            return PostResult(self.slug, False, detail=(errs or str(parsed))[:400])
        thing = j.get("data", {})
        # The submit response rarely contains the permalink directly; request it
        # is not a guarantee, so present the sub + id for verification.
        return PostResult(self.slug, True,
                          url=thing.get("url", "") or f"https://reddit.com/r/{payload.get('sr', '')}/",
                          detail=f"submitted (id {thing.get('id', '?')}) - public, review subreddit rules first")

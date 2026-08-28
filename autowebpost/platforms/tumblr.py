"""Tumblr publisher - free, DA ~91, DoFollow text posts.

Create ONE app at https://www.tumblr.com/oauth/apps to get consumer key/secret,
then authenticate once (the flow prints a URL to click):
    python -m autowebpost.cli connect tumblr
Tokens are cached in data/.tumblr_token.

Posting is signed with OAuth 1.0a (implemented below with stdlib only).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse

import requests

from ..config import DATA_DIR, get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher
from .htmlutil import markdown_to_html

TOKEN_FILE = DATA_DIR / ".tumblr_token"
REQUEST_URL = "https://www.tumblr.com/oauth/request_token"
AUTHORIZE_URL = "https://www.tumblr.com/oauth/authorize"
ACCESS_URL = "https://www.tumblr.com/oauth/access_token"
POST_URL = "https://api.tumblr.com/v2/blog/{blog}/post"


def _oauth1_header(method: str, url: str, params: dict, cons_key: str, cons_sec: str,
                   tok: str, tok_sec: str) -> str:
    """Sign a request with OAuth 1.0a HMAC-SHA1 (stdlib only)."""
    allp = dict(params)
    allp.update({
        "oauth_consumer_key": cons_key,
        "oauth_token": tok,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": secrets.token_hex(16),
        "oauth_version": "1.0",
    })
    base_str = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote("&".join(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
                                    for k, v in sorted(allp.items())), safe=""),
    ])
    key = f"{urllib.parse.quote(cons_sec, safe='')}&{urllib.parse.quote(tok_sec, safe='')}"
    sig = base64.b64encode(hmac.new(key.encode(), base_str.encode(), hashlib.sha1).digest()).decode()
    header_items = [
        f'oauth_consumer_key="{urllib.parse.quote(cons_key, safe="")}"',
        f'oauth_token="{urllib.parse.quote(tok, safe="")}"',
        'oauth_signature_method="HMAC-SHA1"',
        f'oauth_signature="{urllib.parse.quote(sig, safe="")}"',
        f'oauth_timestamp="{allp["oauth_timestamp"]}"',
        f'oauth_nonce="{urllib.parse.quote(allp["oauth_nonce"], safe="")}"',
        'oauth_version="1.0"',
    ]
    return "OAuth " + ", ".join(header_items)


def run_connect_flow() -> str:
    """One-time OAuth dance. Prints a URL to open, asks for the verifier."""
    ck, cs = get_secret("TUMBLR_CONSUMER_KEY"), get_secret("TUMBLR_CONSUMER_SECRET")
    if not (ck and cs):
        raise RuntimeError("Set TUMBLR_CONSUMER_KEY / TUMBLR_CONSUMER_SECRET in .env first (create an app at https://www.tumblr.com/oauth/apps)")
    resp = requests.post(REQUEST_URL, headers=UA, auth=None,
                         params={"oauth_consumer_key": ck, "oauth_signature_method": "HMAC-SHA1"},
                         timeout=30)
    resp.raise_for_status()
    req_tok = dict(urllib.parse.parse_qsl(resp.text))
    print("\nOpen this URL, click Allow, and paste the oauth_verifier code below:\n")
    print(f"{AUTHORIZE_URL}?oauth_token={req_tok['oauth_token']}\n")
    verifier = input("oauth_verifier: ").strip()
    resp = requests.post(ACCESS_URL, params={"oauth_token": req_tok["oauth_token"], "oauth_verifier": verifier}, headers=UA, timeout=30)
    resp.raise_for_status()
    acc = dict(urllib.parse.parse_qsl(resp.text))
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(f"{acc['oauth_token']}\n{acc['oauth_token_secret']}")
    print(f"\nSaved to {TOKEN_FILE}. You are connected.")
    return acc["oauth_token"]


def _tokens():
    if TOKEN_FILE.exists():
        t, s = TOKEN_FILE.read_text().splitlines()[:2]
        return t.strip(), s.strip()
    return "", ""


class TumblrPublisher(Publisher):
    slug = "tumblr"
    name = "Tumblr"
    env_keys = ["TUMBLR_CONSUMER_KEY", "TUMBLR_CONSUMER_SECRET", "TUMBLR_BLOG"]
    docs = "https://www.tumblr.com/docs/en/api/v2#posts"

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        return {
            "type": "text",
            "title": draft.title,
            "body": markdown_to_html(draft.body_markdown),
            "tags": ",".join(draft.tags[:10]),
            "canonical_url": draft.canonical_url or None,
            "format": "html",
            "state": "draft" if draft.language == "review" else "published",
        }

    def _publish_live(self, draft, persona, payload, as_draft: bool = True, **kw) -> PostResult:
        blog = get_secret("TUMBLR_BLOG")
        tok, tok_sec = _tokens()
        if not tok:
            return PostResult(self.slug, False, detail='not connected - run: python -m autowebpost.cli connect tumblr')
        payload = {k: v for k, v in payload.items() if v is not None}
        payload["state"] = "draft" if as_draft else "published"
        url = POST_URL.format(blog=blog)
        auth = _oauth1_header("POST", url, payload,
                              get_secret("TUMBLR_CONSUMER_KEY"), get_secret("TUMBLR_CONSUMER_SECRET"),
                              tok, tok_sec)
        r = requests.post(url, headers={"Authorization": auth, **UA}, data=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get("meta", {}).get("status") not in (200, 201):
            return PostResult(self.slug, False, detail=str(data))
        return PostResult(self.slug, True, url=f"https://{blog}", detail=f"post id {data['response']['id']} ({payload['state']})")

"""Reddit adapter: payload shape, OAuth request, and success/error handling."""
from __future__ import annotations

import pytest

from autowebpost.platforms import get
from autowebpost.platforms.reddit import AUTH_URL, SUBMIT_URL


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.calls = []

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self.payload

    @property
    def text(self):
        return str(self.json())


def make_post_stub(monkeypatch, submit=True, errors=None):
    """Return FakeResponse list capture; responses keyed by URL."""
    responses = []

    def fake_post(url, *a, **k):
        url = str(url)
        if url.startswith(AUTH_URL):
            payload = {"access_token": "tok123"}
        elif errors is not None:
            payload = {"json": {"success": False, "errors": [errors]}}
        else:
            payload = {"json": {"success": submit, "data": {"id": "abc123", "url": "https://redd.it/abc123"}}}
        r = FakeResponse(payload)
        r.calls.append((url, k))
        responses.append(r)
        return r


    monkeypatch.setattr("requests.post", fake_post)
    return responses


def _env(monkeypatch):
    for k in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME",
              "REDDIT_PASSWORD"):
        monkeypatch.setenv(k, f"{k}-val")
    monkeypatch.setenv("REDDIT_SUBREDDIT", "automation")


class TestPayload:
    def test_link_submission_when_canonical_set(self, draft, persona, monkeypatch):
        _env(monkeypatch)
        p = get("reddit").build_payload(draft, persona)
        assert p["kind"] == "link"
        assert p["url"] == draft.canonical_url
        assert p["sr"] == "automation"

    def test_self_submission_without_canonical(self, minimal_draft, persona, monkeypatch):
        _env(monkeypatch)
        p = get("reddit").build_payload(minimal_draft, persona)
        assert p["kind"] == "self"
        assert p["url"] == ""
        assert minimal_draft.title in p["title"]

    def test_subreddit_is_normalised(self, draft, persona, monkeypatch):
        monkeypatch.setenv("REDDIT_SUBREDDIT", "r/automation")
        assert get("reddit").build_payload(draft, persona)["sr"] == "automation"

    def test_missing_subreddit_uses_test(self, minimal_draft, persona, monkeypatch):
        monkeypatch.delenv("REDDIT_SUBREDDIT", raising=False)
        assert get("reddit").build_payload(minimal_draft, persona)["sr"] == "test"


class TestLive:
    @pytest.fixture(autouse=True)
    def fresh_token(self):
        # The registry holds one RedditPublisher instance; clear its OAuth cache
        # between tests so each one exercises the auth round-trip deterministically.
        get("reddit")._token = ""

    def test_live_refuses_without_allow_public(self, draft, persona, monkeypatch):
        _env(monkeypatch)
        result = get("reddit").publish(draft, persona, live=True)
        assert result.ok is False
        assert "no draft mode" in result.detail
        assert "AUTOWEBPOST_ALLOW_PUBLIC" in result.detail

    def test_enable_public_env_allows_live(self, draft, persona, monkeypatch):
        _env(monkeypatch)
        monkeypatch.setenv("AUTOWEBPOST_ALLOW_PUBLIC", "1")
        responses = make_post_stub(monkeypatch, submit=True)
        result = get("reddit").publish(draft, persona, live=True)
        assert result.ok is True
        assert len(responses) == 2

    def test_live_fetches_token_then_submits(self, draft, persona, monkeypatch):
        _env(monkeypatch)
        responses = make_post_stub(monkeypatch, submit=True)
        result = get("reddit").publish(draft, persona, live=True, allow_public=True)
        assert result.ok is True
        assert result.url == "https://redd.it/abc123"
        assert "abc123" in result.detail
        # auth is requested exactly once; submit follows
        assert len(responses) == 2
        assert responses[0].calls[0][0] == AUTH_URL
        assert responses[1].calls[0][0] == SUBMIT_URL

    def test_live_reports_api_errors(self, draft, persona, monkeypatch):
        _env(monkeypatch)
        make_post_stub(monkeypatch, errors=["BAD_SR", "that subreddit doesn't exist"])
        result = get("reddit").publish(draft, persona, live=True, allow_public=True)
        assert result.ok is False
        assert "that subreddit doesn't exist" in result.detail

    def test_live_missing_env_blocks_without_request(self, draft, persona, monkeypatch):
        for k in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"):
            monkeypatch.delenv(k, raising=False)
        result = get("reddit").publish(draft, persona, live=True, allow_public=True)
        assert result.ok is False
        assert "REDDIT_CLIENT_ID" in result.detail

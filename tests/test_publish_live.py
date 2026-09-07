"""The live publish path, with HTTP mocked out.

These are the calls that touch real accounts, so they are the ones most worth
testing - but nothing here reaches the network. Each test stubs `requests` and
asserts on the exact request the adapter built.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from autowebpost.platforms import get


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload=None, status=200, text=""):
        self._payload = payload if payload is not None else {}
        self.status_code = status
        self.text = text or json.dumps(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


@pytest.fixture
def calls(monkeypatch):
    """Capture every HTTP call and return them; responses come from `reply`."""
    recorded = []

    def make(overrides):
        def _req(method):
            def call(url, **kw):
                recorded.append({"method": method, "url": url, **kw})
                key = (method, url)
                for pattern, resp in overrides.items():
                    if pattern in url:
                        return resp if isinstance(resp, FakeResponse) else FakeResponse(**resp)
                return FakeResponse({})
            return call
        return _req

    recorded.set = make
    monkeypatch.setattr(requests, "get", make({}))
    monkeypatch.setattr(requests, "post", make({}))
    monkeypatch.setattr(requests, "put", make({}))
    return recorded


def stub(monkeypatch, mapping):
    """Route HTTP calls to canned responses.

    Keys are either a URL substring ("api/posts") or a (method, substring) pair
    when GET and POST to the same URL must differ.
    """
    recorded = []

    def resolve(method, url, kw):
        for key, resp in mapping.items():
            if isinstance(key, tuple):
                wanted_method, pattern = key
                if wanted_method != method or pattern not in url:
                    continue
            elif key not in url:
                continue
            return resp(url, kw) if callable(resp) else (
                resp if isinstance(resp, FakeResponse) else FakeResponse(**resp))
        return FakeResponse({})

    def call(method):
        def _req(url, **kw):
            recorded.append({"method": method, "url": url, **kw})
            return resolve(method, url, kw)
        return _req

    monkeypatch.setattr(requests, "get", call("GET"))
    monkeypatch.setattr(requests, "post", call("POST"))
    monkeypatch.setattr(requests, "put", call("PUT"))
    return recorded


class TestDevTo:
    def test_posts_a_draft_and_returns_the_url(self, draft, persona, monkeypatch):
        monkeypatch.setenv("DEVTO_API_KEY", "key-123")
        rec = stub(monkeypatch, {"dev.to/api/articles": FakeResponse({"url": "https://dev.to/x"})})

        r = get("devto").publish(draft, persona, live=True)

        assert r.ok is True and r.url == "https://dev.to/x"
        assert rec[0]["url"] == "https://dev.to/api/articles"
        assert rec[0]["headers"]["api-key"] == "key-123"
        assert rec[0]["json"]["article"]["published"] is False  # draft by default
        assert r.dry_run is False

    def test_sends_canonical_url_and_at_most_four_tags(self, draft, persona, monkeypatch):
        monkeypatch.setenv("DEVTO_API_KEY", "k")
        rec = stub(monkeypatch, {"dev.to/api/articles": FakeResponse({"url": "u"})})
        get("devto").publish(draft, persona, live=True)
        body = rec[0]["json"]["article"]
        assert body["canonical_url"] == draft.canonical_url
        assert len(body["tags"]) <= 4


class TestTelegraph:
    def test_creates_a_page_with_a_cached_token(self, draft, persona, monkeypatch):
        monkeypatch.setenv("TELEGRAPH_TOKEN", "tok")
        rec = stub(monkeypatch, {"createPage": FakeResponse(
            {"ok": True, "result": {"url": "https://telegra.ph/My-Page"}})})

        r = get("telegraph").publish(draft, persona, live=True)

        assert r.ok is True and r.url == "https://telegra.ph/My-Page"
        sent = rec[0]["json"]
        assert sent["access_token"] == "tok"          # real token, not the placeholder
        assert sent["title"] == draft.title
        assert "<!--" not in json.dumps(sent)         # no EDIT-ME markers on a live page

    def test_api_error_is_reported_not_raised(self, draft, persona, monkeypatch):
        monkeypatch.setenv("TELEGRAPH_TOKEN", "tok")
        stub(monkeypatch, {"createPage": FakeResponse({"ok": False, "error": "CONTENT_TOO_BIG"})})
        r = get("telegraph").publish(draft, persona, live=True)
        assert r.ok is False and "CONTENT_TOO_BIG" in r.detail

    def test_drops_local_images_from_the_payload(self, draft, persona, monkeypatch):
        """Regression: relative image paths (images/hero.jpg) were shipped to
        telegra.ph as-is, producing broken <img> tags on the live page."""
        monkeypatch.setenv("TELEGRAPH_TOKEN", "tok")
        rec = stub(monkeypatch, {"createPage": FakeResponse(
            {"ok": True, "result": {"url": "u"}})})
        get("telegraph").publish(draft, persona, live=True)
        nodes = rec[0]["json"]["content"]
        assert not [n for n in nodes if n.get("tag") == "img"]

    def test_children_are_a_flat_node_list(self, draft, persona, monkeypatch):
        """Regression: children were double-nested ([[...]]), which Telegraph rejects."""
        monkeypatch.setenv("TELEGRAPH_TOKEN", "tok")
        rec = stub(monkeypatch, {"createPage": FakeResponse(
            {"ok": True, "result": {"url": "u"}})})
        get("telegraph").publish(draft, persona, live=True)

        def walk(ns):
            for n in ns:
                if isinstance(n, str):
                    continue
                assert isinstance(n, dict), f"node is {type(n).__name__}, not a str/dict"
                walk(n.get("children") or [])
        walk(rec[0]["json"]["content"])


class TestWordPress:
    def test_creates_a_draft_post_with_basic_auth(self, draft, persona, monkeypatch):
        monkeypatch.setenv("WP_SITE", "https://blog.example.com")
        monkeypatch.setenv("WP_USER", "admin")
        monkeypatch.setenv("WP_APP_PASSWORD", "app pass")
        rec = stub(monkeypatch, {"wp-json/wp/v2/posts": FakeResponse(
            {"link": "https://blog.example.com/post", "id": 7})})

        r = get("wordpress").publish(draft, persona, live=True)

        assert r.ok is True and r.url == "https://blog.example.com/post"
        assert rec[0]["url"] == "https://blog.example.com/wp-json/wp/v2/posts"
        assert rec[0]["headers"]["Authorization"].startswith("Basic ")
        assert rec[0]["json"]["status"] == "draft"
        assert "created as DRAFT" in r.detail


class TestGitHubPages:
    def test_commits_a_jekyll_post(self, draft, persona, monkeypatch):
        import base64
        monkeypatch.setenv("GITHUB_REPO", "octocat/octocat.github.io")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
        rec = stub(monkeypatch, {
            # GET 404 = the file does not exist yet, so no sha is sent
            ("GET", "api.github.com/repos"): FakeResponse({}, status=404),
            ("PUT", "api.github.com/repos"): FakeResponse({"content": {}}),
        })

        r = get("githubpages").publish(draft, persona, live=True)

        put = [c for c in rec if c["method"] == "PUT"][0]
        # the Contents API carries the path in the URL, not the request body
        assert "/_posts/" in put["url"]
        assert put["url"].endswith(f"{draft.slug}.md")
        assert draft.title in base64.b64decode(put["json"]["content"]).decode()
        assert r.ok is True and r.url.startswith("https://octocat.github.io/")

    def test_includes_sha_when_the_file_already_exists(self, draft, persona, monkeypatch):
        monkeypatch.setenv("GITHUB_REPO", "octocat/octocat.github.io")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
        rec = stub(monkeypatch, {
            ("GET", "api.github.com/repos"): FakeResponse({"sha": "abc123"}),
            ("PUT", "api.github.com/repos"): FakeResponse({"content": {}}),
        })
        get("githubpages").publish(draft, persona, live=True)
        put = [c for c in rec if c["method"] == "PUT"][0]
        assert put["json"]["sha"] == "abc123"   # required to overwrite an existing file


class TestBlogger:
    def test_inserts_a_draft_post(self, draft, persona, monkeypatch):
        monkeypatch.setenv("BLOGGER_BLOG_ID", "123")
        monkeypatch.setenv("BLOGGER_ACCESS_TOKEN", "ya29.x")
        rec = stub(monkeypatch, {"blogger.googleapis.com": FakeResponse(
            {"url": "https://blog.blogspot.com/x", "id": "99"})})

        r = get("blogger").publish(draft, persona, live=True)

        assert r.ok is True and r.url == "https://blog.blogspot.com/x"
        assert "isDraft=true" in rec[0]["url"]
        assert rec[0]["headers"]["Authorization"] == "Bearer ya29.x"
        assert rec[0]["json"]["labels"] == draft.tags


class TestWriteAs:
    def test_posts_anonymously_without_credentials(self, draft, persona, monkeypatch):
        for k in ("WRITEAS_ALIAS", "WRITEAS_PASSWORD", "WRITEAS_INSTANCE"):
            monkeypatch.delenv(k, raising=False)
        rec = stub(monkeypatch, {"api/posts": FakeResponse({"data": {"slug": "abc"}})})

        r = get("writeas").publish(draft, persona, live=True)

        assert r.ok is True and r.url == "https://write.as/abc"
        assert not [c for c in rec if "auth/login" in c["url"]]   # no login attempted
        assert "Authorization" not in rec[0]["headers"]

    def test_warns_to_save_the_token_on_anonymous_posts(self, draft, persona, monkeypatch):
        """An anonymous write.as post can only be edited with the returned token."""
        for k in ("WRITEAS_ALIAS", "WRITEAS_PASSWORD", "WRITEAS_INSTANCE"):
            monkeypatch.delenv(k, raising=False)
        stub(monkeypatch, {"api/posts": FakeResponse(
            {"data": {"slug": "abc", "token": "edit-token"}})})
        r = get("writeas").publish(draft, persona, live=True)
        assert r.ok is True
        assert "SAVE the post token" in r.detail

    def test_logs_in_when_credentials_are_set(self, draft, persona, monkeypatch):
        monkeypatch.setenv("WRITEAS_ALIAS", "me")
        monkeypatch.setenv("WRITEAS_PASSWORD", "pw")
        rec = stub(monkeypatch, {
            "auth/login": FakeResponse({"data": {"access_token": "tok"}}),
            "api/posts": FakeResponse({"data": {"slug": "abc"}}),
        })
        r = get("writeas").publish(draft, persona, live=True)
        assert r.ok is True
        assert "auth/login" in rec[0]["url"]                  # logged in first
        assert rec[1]["headers"]["Authorization"] == "Token tok"

    def test_honours_a_custom_instance(self, draft, persona, monkeypatch):
        monkeypatch.setenv("WRITEAS_INSTANCE", "https://writefreely.example")
        rec = stub(monkeypatch, {"api/posts": FakeResponse({"data": {"slug": "s"}})})
        r = get("writeas").publish(draft, persona, live=True)
        assert r.url == "https://writefreely.example/s"
        assert rec[0]["url"].startswith("https://writefreely.example")


class TestHashnode:
    def test_publishes_and_flags_the_pro_requirement(self, draft, persona, monkeypatch):
        monkeypatch.setenv("HASHNODE_TOKEN", "hn")
        monkeypatch.setenv("HASHNODE_PUBLICATION_ID", "pub-1")
        rec = stub(monkeypatch, {"gql.hashnode.com": FakeResponse(
            {"data": {"publishPost": {"post": {"url": "https://h.com/x", "slug": "x",
                                               "id": "1"}}}})})

        r = get("hashnode").publish(draft, persona, live=True)

        assert r.ok is True and r.url == "https://h.com/x"
        assert "Pro" in r.detail
        inp = rec[0]["json"]["variables"]["input"]
        assert inp["publicationId"] == "pub-1"
        assert inp["settings"]["isDraft"] is True     # drafts by default

    def test_graphql_errors_are_surfaced(self, draft, persona, monkeypatch):
        monkeypatch.setenv("HASHNODE_TOKEN", "hn")
        monkeypatch.setenv("HASHNODE_PUBLICATION_ID", "pub-1")
        stub(monkeypatch, {"gql.hashnode.com": FakeResponse(
            {"errors": [{"message": "Forbidden: Pro required"}]})})
        r = get("hashnode").publish(draft, persona, live=True)
        assert r.ok is False and "Pro required" in r.detail


class TestMastodon:
    def test_posts_a_snippet_with_the_link(self, draft, persona, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE", "https://mastodon.social/")
        monkeypatch.setenv("MASTODON_TOKEN", "mt")
        rec = stub(monkeypatch, {"api/v1/statuses": FakeResponse(
            {"url": "https://mastodon.social/@u/1"})})

        r = get("mastodon").publish(draft, persona, live=True)

        assert r.ok is True and r.url == "https://mastodon.social/@u/1"
        status = [c for c in rec if "api/v1/statuses" in c["url"]][0]
        assert status["url"] == "https://mastodon.social/api/v1/statuses"  # slash normalised
        assert draft.canonical_url in status["json"]["status"]
        assert len(status["json"]["status"]) <= 495

    def test_skips_upload_when_the_image_is_not_local(self, draft, persona, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_TOKEN", "mt")
        draft.images[0].url = "https://cdn.example.com/a.jpg"   # already remote
        stub(monkeypatch, {"api/v1/statuses": FakeResponse({"url": "u"})})
        rec = stub(monkeypatch, {"api/v1/statuses": FakeResponse({"url": "u"})})
        get("mastodon").publish(draft, persona, live=True)
        assert not [c for c in rec if "media" in c["url"]]

    def test_media_upload_failure_does_not_block_the_post(self, draft, persona,
                                                          monkeypatch, tmp_path):
        monkeypatch.setenv("MASTODON_INSTANCE", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_TOKEN", "mt")
        img = tmp_path / "hero.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"0" * 6000)
        draft.images[0].path, draft.images[0].url = str(img), ""
        rec = stub(monkeypatch, {
            "api/v2/media": FakeResponse({}, status=413),
            "api/v1/statuses": FakeResponse({"url": "https://mastodon.social/@u/1"}),
        })
        r = get("mastodon").publish(draft, persona, live=True)
        assert r.ok is True
        assert "media_ids" not in [c for c in rec if "statuses" in c["url"]][0]["json"]

    def test_long_text_is_split_into_numbered_chunks(self):
        from autowebpost.platforms.mastodon import _split
        parts = _split("para " * 400)
        assert len(parts) > 1
        assert all(len(p) <= 480 for p in parts)


class TestTumblr:
    def test_requires_the_one_time_connect_flow(self, draft, persona, monkeypatch, tmp_path):
        import autowebpost.platforms.tumblr as tumblr_mod
        monkeypatch.setattr(tumblr_mod, "TOKEN_FILE", tmp_path / "no-token")
        for k in ("TUMBLR_CONSUMER_KEY", "TUMBLR_CONSUMER_SECRET", "TUMBLR_BLOG"):
            monkeypatch.setenv(k, "x")
        r = get("tumblr").publish(draft, persona, live=True)
        assert r.ok is False and "connect tumblr" in r.detail

    def test_signs_and_posts_with_a_cached_token(self, draft, persona, monkeypatch, tmp_path):
        import autowebpost.platforms.tumblr as tumblr_mod
        tok_file = tmp_path / ".tumblr_token"
        tok_file.write_text("oauth-tok\noauth-secret\n", encoding="utf-8")
        monkeypatch.setattr(tumblr_mod, "TOKEN_FILE", tok_file)
        monkeypatch.setenv("TUMBLR_CONSUMER_KEY", "ck")
        monkeypatch.setenv("TUMBLR_CONSUMER_SECRET", "cs")
        monkeypatch.setenv("TUMBLR_BLOG", "myblog.tumblr.com")

        rec = stub(monkeypatch, {"api.tumblr.com": FakeResponse(
            {"meta": {"status": 201}, "response": {"id": "42"}})})

        r = get("tumblr").publish(draft, persona, live=True)

        assert r.ok is True and r.url == "https://myblog.tumblr.com"
        assert rec[0]["url"] == "https://api.tumblr.com/v2/blog/myblog.tumblr.com/post"
        auth = rec[0]["headers"]["Authorization"]
        assert auth.startswith("OAuth ") and "oauth_signature=" in auth
        assert rec[0]["data"]["state"] == "draft"       # drafts by default

    def test_api_level_error_is_reported(self, draft, persona, monkeypatch, tmp_path):
        import autowebpost.platforms.tumblr as tumblr_mod
        tok_file = tmp_path / ".tumblr_token"
        tok_file.write_text("t\ns\n", encoding="utf-8")
        monkeypatch.setattr(tumblr_mod, "TOKEN_FILE", tok_file)
        for k, v in (("TUMBLR_CONSUMER_KEY", "ck"), ("TUMBLR_CONSUMER_SECRET", "cs"),
                     ("TUMBLR_BLOG", "b.tumblr.com")):
            monkeypatch.setenv(k, v)
        stub(monkeypatch, {"api.tumblr.com": FakeResponse(
            {"meta": {"status": 401, "msg": "Not authorized"}})})
        r = get("tumblr").publish(draft, persona, live=True)
        assert r.ok is False and "Not authorized" in r.detail

    def test_oauth_header_contains_the_required_fields(self):
        from autowebpost.platforms.tumblr import _oauth1_header
        header = _oauth1_header("POST", "https://api.tumblr.com/v2/blog/b/post",
                                {"type": "text"}, "ck", "cs", "tok", "ts")
        for field in ("oauth_consumer_key", "oauth_signature_method", "oauth_signature",
                      "oauth_timestamp", "oauth_nonce", "oauth_version", "oauth_token"):
            assert field in header


class TestMedium:
    def test_manual_import_flow_returns_the_canonical_url(self, draft, persona):
        r = get("medium").publish(draft, persona, live=True)
        assert r.ok is True and r.url == draft.canonical_url
        assert "Import a story" in r.detail

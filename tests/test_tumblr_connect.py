"""The one-time `connect tumblr` OAuth dance (prompts + HTTP mocked)."""
from __future__ import annotations

import pytest
import requests

import autowebpost.platforms.tumblr as tumblr_mod
from autowebpost.platforms.tumblr import _oauth1_header, _tokens, run_connect_flow


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("boom", response=self)

    def json(self):
        return {}


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    p = tmp_path / ".tumblr_token"
    monkeypatch.setattr(tumblr_mod, "TOKEN_FILE", p)
    return p


class TestTokens:
    def test_empty_when_never_connected(self, token_file):
        assert _tokens() == ("", "")

    def test_reads_a_cached_pair(self, token_file):
        token_file.write_text("tok\nsecret\n", encoding="utf-8")
        assert _tokens() == ("tok", "secret")

    def test_tolerates_extra_lines(self, token_file):
        token_file.write_text("tok\nsecret\nstray\n", encoding="utf-8")
        assert _tokens() == ("tok", "secret")


class TestConnectFlow:
    def test_refuses_without_consumer_credentials(self, token_file, monkeypatch):
        for key in ("TUMBLR_CONSUMER_KEY", "TUMBLR_CONSUMER_SECRET"):
            monkeypatch.delenv(key, raising=False)
        with pytest.raises(RuntimeError, match="TUMBLR_CONSUMER_KEY"):
            run_connect_flow()

    def test_exchanges_a_verifier_for_tokens(self, token_file, monkeypatch, capsys):
        monkeypatch.setenv("TUMBLR_CONSUMER_KEY", "ck")
        monkeypatch.setenv("TUMBLR_CONSUMER_SECRET", "cs")
        monkeypatch.setattr("builtins.input", lambda prompt="": "verifier-123")

        requests_seen = []

        def _post(url, **kw):
            requests_seen.append(url)
            if "request_token" in url:
                return FakeResponse("oauth_token=req-tok&oauth_token_secret=req-sec")
            return FakeResponse("oauth_token=acc-tok&oauth_token_secret=acc-sec")

        monkeypatch.setattr(requests, "post", _post)

        token = run_connect_flow()

        assert token == "acc-tok"
        assert len(requests_seen) == 2
        assert "request_token" in requests_seen[0]
        assert "access_token" in requests_seen[1]
        assert token_file.read_text().splitlines() == ["acc-tok", "acc-sec"]
        assert "Open this URL" in capsys.readouterr().out

    def test_a_failed_request_token_aborts(self, token_file, monkeypatch):
        monkeypatch.setenv("TUMBLR_CONSUMER_KEY", "ck")
        monkeypatch.setenv("TUMBLR_CONSUMER_SECRET", "cs")
        monkeypatch.setattr(requests, "post", lambda url, **kw: FakeResponse("", status=401))
        with pytest.raises(requests.HTTPError):
            run_connect_flow()
        assert not token_file.exists()


class TestOAuth1Header:
    def test_is_a_well_formed_oauth_header(self):
        header = _oauth1_header("POST", "https://api.tumblr.com/v2/blog/b/post",
                                {"type": "text", "body": "<p>hi</p>"}, "ck", "cs", "t", "ts")
        assert header.startswith("OAuth ")
        for field in ("oauth_consumer_key", "oauth_token", "oauth_signature_method",
                      "oauth_signature", "oauth_timestamp", "oauth_nonce", "oauth_version"):
            assert field in header

    def test_signature_depends_on_the_payload(self):
        url = "https://api.tumblr.com/v2/blog/b/post"
        a = _oauth1_header("POST", url, {"body": "one"}, "ck", "cs", "t", "ts")
        b = _oauth1_header("POST", url, {"body": "two"}, "ck", "cs", "t", "ts")
        assert a != b

    def test_percent_encodes_special_characters(self):
        header = _oauth1_header("POST", "https://api.tumblr.com/v2/blog/b/post",
                                {"body": "<p>a & b</p>"}, "ck", "cs", "t", "ts")
        assert "<p>" not in header          # raw markup must not break the header
        assert "oauth_signature=" in header

"""Smoke command: safe-by-default connectivity checks with a strict live gate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import autowebpost.smoke as smoke
from autowebpost import cli
from autowebpost.smoke import CONFIRM_TEXT, SmokeReport


@pytest.fixture(autouse=True)
def smoke_dir_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "SMOKE_DIR", tmp_path / "smoke")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload

    @property
    def text(self):
        return str(self.json())


def _post_stub(monkeypatch, api="devto"):
    def fake_post(url, *a, **k):
        url = str(url)
        if "oauth.reddit.com" in url or "www.reddit.com/api/v1/access_token" in url:
            if "access_token" in url:
                return FakeResponse({"access_token": "tok"})
            return FakeResponse({"json": {"success": True,
                                          "data": {"id": "abc", "url": "https://redd.it/abc"}}})
        if "dev.to" in url and api == "devto":
            return FakeResponse({"url": "https://dev.to/x/1"})
        if "blogger" in url and api == "blogger":
            return FakeResponse({"url": "https://x.blogspot.com/p", "id": "1"})
        if "mastodon.social" in url and "api/v1/statuses" in url:
            return FakeResponse({"url": "https://mastodon.social/@x/1"})
        return FakeResponse({"ok": True, "result": {"url": "https://telegra.ph/x"}})
    monkeypatch.setattr("requests.post", fake_post)


class TestDraft:
    def test_smoke_draft_is_clearly_a_test(self):
        d = smoke.make_smoke_draft()
        assert d.generator == "smoke"
        assert d.primary_keyword == "autowebpost smoke test"
        assert "smoke-test" in d.tags


class TestGates:
    def test_dry_run_needs_no_credentials(self, persona, monkeypatch):
        report = smoke.run_smoke(draft=smoke.make_smoke_draft(),
                                 platforms=["devto", "wordpress", "blogger"], live=False)
        assert report.allowed is True
        assert report.ok is True
        assert all(r.ok and r.dry_run for r in report.results)

    def test_live_requires_explicit_enable(self, monkeypatch):
        monkeypatch.delenv(smoke.ALLOW_LIVE_ENV, raising=False)
        report = smoke.run_smoke(platforms=["devto"], live=True, confirm=CONFIRM_TEXT,
                                 allow_live=False, save_report=False)
        assert report.allowed is False
        assert smoke.ALLOW_LIVE_ENV in report.gate_message
        assert report.results == []

    def test_live_requires_confirm_text(self, monkeypatch):
        monkeypatch.setenv(smoke.ALLOW_LIVE_ENV, "1")
        report = smoke.run_smoke(platforms=["devto"], live=True, confirm="yes",
                                 allow_live=False, save_report=False)
        assert report.allowed is False
        assert CONFIRM_TEXT in report.gate_message

    def test_public_platform_requires_force_live(self, monkeypatch):
        monkeypatch.setenv(smoke.ALLOW_LIVE_ENV, "1")
        report = smoke.run_smoke(platforms=["mastodon"], live=True, confirm=CONFIRM_TEXT,
                                 force=False, save_report=False)
        assert report.allowed is False
        assert "--force" in report.gate_message
        assert "mastodon" in report.gate_message


class TestLiveGated:
    def test_live_draft_safe_platform_is_allowed_and_attempted(self, monkeypatch):
        monkeypatch.setenv(smoke.ALLOW_LIVE_ENV, "1")
        monkeypatch.setenv("DEVTO_API_KEY", "k")
        _post_stub(monkeypatch, api="devto")
        report = smoke.run_smoke(platforms=["devto"], live=True, confirm=CONFIRM_TEXT,
                                 force=False, save_report=False)
        assert report.allowed is True
        assert report.ok is True
        assert report.results[0].url == "https://dev.to/x/1"

    def test_force_allows_public_platform(self, monkeypatch):
        monkeypatch.setenv(smoke.ALLOW_LIVE_ENV, "1")
        monkeypatch.setenv("MASTODON_INSTANCE", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_TOKEN", "tok")
        _post_stub(monkeypatch, api="mastodon")
        report = smoke.run_smoke(platforms=["mastodon"], live=True, confirm=CONFIRM_TEXT,
                                 force=True, save_report=False)
        assert report.allowed is True
        assert report.ok is True

    def test_force_live_reddit_uses_allow_public(self, monkeypatch):
        # Reddit refuses `live=True` unless the caller passes allow_public; smoke
        # must pass it through when --force is set.
        monkeypatch.setenv(smoke.ALLOW_LIVE_ENV, "1")
        monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "sec")
        monkeypatch.setenv("REDDIT_USERNAME", "u")
        monkeypatch.setenv("REDDIT_PASSWORD", "p")
        monkeypatch.setenv("REDDIT_SUBREDDIT", "automation")
        _post_stub(monkeypatch)
        report = smoke.run_smoke(platforms=["reddit"], live=True, confirm=CONFIRM_TEXT,
                                 force=True, save_report=False)
        assert report.allowed is True
        assert report.ok is True

    def test_blocked_live_is_reported_not_attempted(self, monkeypatch):
        monkeypatch.delenv(smoke.ALLOW_LIVE_ENV, raising=False)
        report = smoke.run_smoke(platforms=["telegraph"], live=True, confirm=CONFIRM_TEXT,
                                 force=False, save_report=False)
        assert report.allowed is False
        assert report.results == []


class TestReport:
    def test_report_is_saved_as_json(self, tmp_path):
        report = smoke.run_smoke(platforms=["devto"], live=False)
        last = smoke.SMOKE_DIR / "smoke-last.json"
        assert last.exists()
        data = json.loads(last.read_text(encoding="utf-8"))
        assert data["live"] is False
        assert data["platforms"] == ["devto"]
        assert data["results"][0]["dry_run"] is True
        assert isinstance(report, SmokeReport)

    def test_cli_dry_run_exits_zero_and_lists_results(self, capsys, monkeypatch):
        r = cli.main(["smoke", "--no-save", "--platforms", "devto"])
        assert r == 0
        out = capsys.readouterr().out
        assert "SMOKE DRY-RUN" in out
        assert "devto" in out


class TestSmokeResult:
    def test_summary_dry_run(self):
        assert "DRY-RUN" in smoke.SmokeResult("devto", ok=True, dry_run=True).summary()

    def test_summary_skip(self):
        assert "SKIP" in smoke.SmokeResult("mastodon", skipped=True).summary()

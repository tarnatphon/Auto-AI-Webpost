"""Drip queue: add / list / remove / run-due, with the queue file redirected to tmp."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from autowebpost import scheduler


@pytest.fixture(autouse=True)
def queue_in_tmp(tmp_path, monkeypatch):
    """Every test uses a throwaway queue file - never data/queue.yaml."""
    monkeypatch.setattr(scheduler, "QUEUE_FILE", tmp_path / "queue.yaml")


def add(draft="output/drafts/x/article.md", platforms=("telegraph",), at=None, delay=0,
        max_attempts=None, retry_minutes=None):
    return scheduler.add(draft, list(platforms), at, delay_minutes=delay,
                         max_attempts=max_attempts or scheduler.DEFAULT_MAX_ATTEMPTS,
                         retry_minutes=retry_minutes or scheduler.DEFAULT_RETRY_MINUTES)


class TestAdd:
    def test_entry_gets_an_id_and_pending_status(self):
        e = add()
        assert e["id"] and e["status"] == "pending"
        assert e["platforms"] == ["telegraph"]

    def test_defaults_to_now_when_no_time_given(self):
        e = add()
        assert datetime.strptime(e["publish_at"], "%Y-%m-%d %H:%M")

    def test_honours_an_explicit_time(self):
        e = add(at="2030-01-01 09:00")
        assert e["publish_at"] == "2030-01-01 09:00"

    def test_stores_the_stagger(self):
        assert add(delay=30)["delay_minutes"] == 30

    def test_accumulates_entries(self):
        add(); add()
        assert len(scheduler.entries()) == 2

    def test_ids_are_unique(self):
        assert add()["id"] != add()["id"]


class TestEntries:
    def test_empty_when_no_file(self):
        assert scheduler.entries() == []

    def test_tolerates_an_empty_file(self):
        scheduler.QUEUE_FILE.write_text("", encoding="utf-8")
        assert scheduler.entries() == []

    def test_tolerates_a_null_file(self):
        """A queue file containing only '---' or whitespace parses as None."""
        scheduler.QUEUE_FILE.write_text("---\n", encoding="utf-8")
        assert scheduler.entries() == []


class TestRemove:
    def test_removes_by_id(self):
        e = add()
        assert scheduler.remove(e["id"]) is True
        assert scheduler.entries() == []

    def test_reports_unknown_id(self):
        assert scheduler.remove("nope") is False

    def test_removes_only_the_target(self):
        keep, drop = add(), add()
        scheduler.remove(drop["id"])
        assert [x["id"] for x in scheduler.entries()] == [keep["id"]]


def stub_telegraph(monkeypatch, ok=True):
    """Stub the two Telegra.ph calls (createAccount + createPage).

    Telegraph is the one platform that publishes with zero credentials, so any
    live-path test involving it MUST stub HTTP or it hits the real site.
    """
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            if ok:
                return {"ok": True, "result": {"url": "https://telegra.ph/Test-09-04"}}
            return {"ok": False, "error": "STUBBED_FAILURE"}

    monkeypatch.setenv("TELEGRAPH_TOKEN", "stub-token")
    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResponse())
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResponse())


class TestRunDue:
    def test_nothing_due_when_scheduled_in_the_future(self, tmp_path):
        add(at="2030-01-01 09:00")
        assert scheduler.run_due() == []

    def test_runs_entries_whose_time_has_come(self, tmp_path):
        from autowebpost.models import ArticleDraft
        folder = tmp_path / "d"
        folder.mkdir()
        (folder / "article.md").write_text(
            ArticleDraft(title="T", slug="t", body_markdown="body").to_markdown(),
            encoding="utf-8")
        add(draft=str(folder / "article.md"), platforms=["telegraph"], at="2000-01-01 09:00")

        done = scheduler.run_due(live=False)
        assert len(done) == 1
        assert done[0]["status"] == "simulated"
        assert done[0]["results"][0]["dry_run"] is True

    def test_already_published_entries_are_skipped(self, tmp_path):
        from autowebpost.models import ArticleDraft
        folder = tmp_path / "d"; folder.mkdir()
        (folder / "article.md").write_text(
            ArticleDraft(title="T", slug="t", body_markdown="b").to_markdown(), encoding="utf-8")
        e = add(draft=str(folder / "article.md"), at="2000-01-01 09:00")
        scheduler.run_due()
        assert scheduler.run_due() == []

    def test_unparseable_time_is_treated_as_due(self, tmp_path):
        from autowebpost.models import ArticleDraft
        folder = tmp_path / "d"; folder.mkdir()
        (folder / "article.md").write_text(
            ArticleDraft(title="T", slug="t", body_markdown="b").to_markdown(), encoding="utf-8")
        add(draft=str(folder / "article.md"), at="not-a-date")
        assert len(scheduler.run_due()) == 1

    def test_missing_draft_file_retries_then_fails(self, tmp_path):
        start = datetime(2000, 1, 1, 9, 0)
        add(draft=str(tmp_path / "gone" / "article.md"), at="2000-01-01 09:00",
            max_attempts=2, retry_minutes=30)
        done = scheduler.run_due(now=start)
        assert len(done) == 1
        assert done[0]["status"] == "retrying"
        assert done[0]["attempts"] == 1
        assert done[0]["next_attempt_at"] == "2000-01-01 09:30"
        assert "cannot load draft" in done[0]["results"][0]["detail"]

        # After the retry window has passed it tries once more, then fails.
        done = scheduler.run_due(now=datetime(2000, 1, 1, 10, 0))
        assert done[0]["status"] == "failed"
        assert done[0]["attempts"] == 2

    def test_regression_unknown_platform_does_not_abort_the_run(self, tmp_path):
        """One typo'd slug used to raise KeyError and kill the entire queue run."""
        from autowebpost.models import ArticleDraft
        folder = tmp_path / "d"; folder.mkdir()
        (folder / "article.md").write_text(
            ArticleDraft(title="T", slug="t", body_markdown="b").to_markdown(), encoding="utf-8")
        add(draft=str(folder / "article.md"), platforms=["myspace"], at="2000-01-01 09:00")

        done = scheduler.run_due(live=False)
        assert len(done) == 1
        assert done[0]["status"] == "failed"
        assert "Unknown publisher" in done[0]["results"][0]["detail"]

    def test_a_failing_platform_marks_the_entry_failed(self, tmp_path):
        from autowebpost.models import ArticleDraft
        folder = tmp_path / "d"; folder.mkdir()
        (folder / "article.md").write_text(
            ArticleDraft(title="T", slug="t", body_markdown="b").to_markdown(), encoding="utf-8")
        add(draft=str(folder / "article.md"), platforms=["myspace", "telegraph"],
            at="2000-01-01 09:00")
        done = scheduler.run_due(live=False)
        assert done[0]["status"] == "failed"
        assert scheduler.entries()[0]["status"] == "failed"

    def test_stagger_is_recorded_not_slept(self, tmp_path):
        from autowebpost.models import ArticleDraft
        folder = tmp_path / "d"; folder.mkdir()
        (folder / "article.md").write_text(
            ArticleDraft(title="T", slug="t", body_markdown="b").to_markdown(), encoding="utf-8")
        add(draft=str(folder / "article.md"), platforms=["telegraph", "devto"],
            at="2000-01-01 09:00", delay=30)
        results = scheduler.run_due(live=False)[0]["results"]
        assert any("staggered" in r.get("note", "") for r in results)

    def _draft(self, tmp_path):
        from autowebpost.models import ArticleDraft
        folder = tmp_path / "d"; folder.mkdir()
        path = folder / "article.md"
        path.write_text(ArticleDraft(title="T", slug="t",
                                     body_markdown="b").to_markdown(), encoding="utf-8")
        return str(path)

    def test_live_run_marks_published_when_every_platform_succeeds(self, tmp_path,
                                                                   monkeypatch):
        """Telegraph needs no credentials, so its live path would really post to
        telegra.ph - stub the HTTP instead of relying on the sandbox being offline."""
        stub_telegraph(monkeypatch, ok=True)
        add(draft=self._draft(tmp_path), platforms=["telegraph"], at="2000-01-01 09:00")
        done = scheduler.run_due(live=True)
        assert done and done[0]["status"] == "published"

    def test_live_failure_retries_then_fails(self, tmp_path, monkeypatch):
        start = datetime(2000, 1, 1, 9, 0)
        stub_telegraph(monkeypatch, ok=False)
        add(draft=self._draft(tmp_path), platforms=["telegraph"], at="2000-01-01 09:00",
            max_attempts=2, retry_minutes=30)
        done = scheduler.run_due(live=True, now=start)
        assert done and done[0]["status"] == "retrying"
        assert done[0]["attempts"] == 1
        assert done[0]["next_attempt_at"] == "2000-01-01 09:30"

        done = scheduler.run_due(live=True, now=datetime(2000, 1, 1, 10, 0))
        assert done and done[0]["status"] == "failed"
        assert done[0]["attempts"] == 2

    def test_unknown_slug_is_never_retried(self, tmp_path):
        add(draft=self._draft(tmp_path), platforms=["myspace"], at="2000-01-01 09:00",
            max_attempts=3, retry_minutes=30)
        done = scheduler.run_due(now=datetime(2000, 1, 1, 9, 0))
        assert done[0]["status"] == "failed"
        assert done[0]["attempts"] == 1
        assert done[0].get("next_attempt_at")  # kept, but status is terminal

    def test_retry_only_reposts_platforms_that_failed(self, tmp_path, monkeypatch):
        start = datetime(2000, 1, 1, 9, 0)
        monkeypatch.setenv("DEVTO_API_KEY", "k")
        monkeypatch.setenv("TELEGRAPH_TOKEN", "stub-token")

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"url": "https://dev.to/x"} if "dev.to" in self._url else {"ok": False, "error": "boom"}

        def fake_post(url, *a, **k):
            r = Resp(); r._url = str(url); return r

        monkeypatch.setattr("requests.post", fake_post)
        add(draft=self._draft(tmp_path), platforms=["devto", "telegraph"],
            at="2000-01-01 09:00", max_attempts=2, retry_minutes=30)
        done = scheduler.run_due(live=True, now=start)
        assert done[0]["status"] == "retrying"
        assert done[0]["platform_status"]["devto"] == "ok"
        assert done[0]["platform_status"]["telegraph"] == "failed"

        done = scheduler.run_due(live=True, now=datetime(2000, 1, 1, 10, 0))
        assert done[0]["status"] == "failed"
        devto_results = [r for r in done[0]["results"] if r.get("platform") == "devto"]
        assert len(devto_results) == 1  # never double-posted

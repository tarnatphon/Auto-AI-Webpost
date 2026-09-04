"""Drip queue: add / list / remove / run-due, with the queue file redirected to tmp."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from autowebpost import scheduler


@pytest.fixture(autouse=True)
def queue_in_tmp(tmp_path, monkeypatch):
    """Every test uses a throwaway queue file - never data/queue.yaml."""
    monkeypatch.setattr(scheduler, "QUEUE_FILE", tmp_path / "queue.yaml")


def add(draft="output/drafts/x/article.md", platforms=("telegraph",), at=None, delay=0):
    return scheduler.add(draft, list(platforms), at, delay_minutes=delay)


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

    def test_missing_draft_file_fails_the_entry_not_the_run(self, tmp_path):
        add(draft=str(tmp_path / "gone" / "article.md"), at="2000-01-01 09:00")
        done = scheduler.run_due()
        assert len(done) == 1
        assert done[0]["status"] == "failed"
        assert "cannot load draft" in done[0]["results"][0]["error"]

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

    def test_live_run_marks_published_only_when_all_succeed(self, tmp_path):
        from autowebpost.models import ArticleDraft
        folder = tmp_path / "d"; folder.mkdir()
        (folder / "article.md").write_text(
            ArticleDraft(title="T", slug="t", body_markdown="b").to_markdown(), encoding="utf-8")
        add(draft=str(folder / "article.md"), platforms=["telegraph"], at="2000-01-01 09:00")
        # no credentials in the environment -> live publish fails cleanly
        done = scheduler.run_due(live=True)
        assert done and done[0]["status"] == "failed"

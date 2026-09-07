"""The review gate model: state, EDIT-ME detection, auto-verified checklist."""
from __future__ import annotations

import pytest

from autowebpost.drafts import save_draft
from autowebpost.models import ArticleDraft, FAQItem, ImageAsset
from autowebpost.review import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    ReviewState,
    checklist_progress,
    checklist_report,
    draft_summary,
    find_edit_me,
    is_publishable,
    iter_draft_folders,
    load_draft_folder,
    load_review,
    review_path,
    save_review,
    set_decision,
    set_notes,
    toggle_checklist,
    unresolved_markers,
)

MARKER = "<!-- EDIT-ME: replace this -->"


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "d"


def clean_draft(**kw):
    """A draft with no EDIT-ME markers, 3 FAQ, 2 refs, canonical, disclosure."""
    base = dict(
        title="Canonical Url: A Clean Draft",   # keyword is in the title
        slug="a-clean-draft",
        primary_keyword="canonical url",
        # 147 chars and contains the keyword: inside the 120-158 window
        meta_description="Canonical url is how cross-posting stays safe. " * 3,
        body_markdown="Body text. **Editorial note** here.\n\nAuthor box for "
                      "Alex Carter.\n",
        faq=[FAQItem(f"Q{i}?", f"A{i}.") for i in range(3)],
        references=["https://a.example", "https://b.example"],
        images=[ImageAsset(path="images/hero.jpg", alt_text="hero diagram")],
        canonical_url="https://yourname.github.io/a-clean-draft.html",
    )
    base.update(kw)
    return ArticleDraft(**base)


class TestReviewState:
    def test_defaults_to_pending(self, folder):
        assert load_review(folder).status == STATUS_PENDING

    def test_round_trips(self, folder):
        save_review(folder, ReviewState(status=STATUS_APPROVED,
                                        checklist={"x": True}, notes="n",
                                        decided_at="2026-09-04T00:00:00Z"))
        r = load_review(folder)
        assert r.status == STATUS_APPROVED
        assert r.checklist == {"x": True}
        assert r.notes == "n"

    def test_state_file_sits_beside_the_article(self, folder):
        save_review(folder, ReviewState())
        assert review_path(folder) == folder / "review.yaml"
        assert review_path(folder).exists()

    def test_unknown_status_falls_back_to_pending(self):
        assert ReviewState.from_dict({"status": "bogus"}).status == STATUS_PENDING

    def test_handles_a_corrupt_state_file(self, folder):
        (folder).mkdir(parents=True, exist_ok=True)
        review_path(folder).write_text("not: a: valid: mapping: [\n", encoding="utf-8")
        assert load_review(folder).status == STATUS_PENDING


class TestDecisions:
    def test_approve_stamps_a_time(self, folder):
        s = set_decision(folder, STATUS_APPROVED)
        assert s.status == STATUS_APPROVED and s.decided_at

    def test_reject(self, folder):
        assert set_decision(folder, STATUS_REJECTED).status == STATUS_REJECTED

    def test_reset_clears_the_timestamp(self, folder):
        set_decision(folder, STATUS_APPROVED)
        s = set_decision(folder, STATUS_PENDING)
        assert s.status == STATUS_PENDING and s.decided_at == ""

    def test_invalid_status_raises(self, folder):
        with pytest.raises(ValueError, match="status must be"):
            set_decision(folder, "maybe")

    def test_decision_persists_across_loads(self, folder):
        set_decision(folder, STATUS_APPROVED)
        assert load_review(folder).status == STATUS_APPROVED


class TestChecklist:
    def test_toggle_persists(self, folder):
        toggle_checklist(folder, "item one", True)
        toggle_checklist(folder, "item two", False)
        r = load_review(folder)
        assert r.checklist == {"item one": True, "item two": False}

    def test_toggle_is_idempotent(self, folder):
        toggle_checklist(folder, "x", True)
        toggle_checklist(folder, "x", True)
        assert load_review(folder).checklist["x"] is True

    def test_notes_persist(self, folder):
        assert set_notes(folder, "needs work").notes == "needs work"

    def test_blank_notes_clear(self, folder):
        set_notes(folder, "x")
        assert set_notes(folder, "").notes == ""


class TestEditMe:
    def test_finds_markers(self):
        assert len(find_edit_me(f"a {MARKER} b {MARKER} c")) == 2

    def test_case_insensitive(self):
        assert len(find_edit_me("<!-- edit-me: x -->")) == 1

    def test_multiline_marker(self):
        assert len(find_edit_me("<!-- EDIT-ME:\nline one\nline two\n-->")) == 1

    def test_none_when_clean(self):
        assert find_edit_me("clean text") == []

    def test_unresolved_markers_look_in_faq_and_references(self):
        d = clean_draft(body_markdown="clean body",
                        faq=[FAQItem("q", f"answer {MARKER}")],
                        references=[f"ref {MARKER}"],
                        canonical_url="")
        assert len(unresolved_markers(d)) == 2

    def test_clean_draft_has_no_markers(self):
        assert unresolved_markers(clean_draft()) == []


class TestAutoChecks:
    def test_clean_draft_passes_the_machine_checkable_items(self, persona):
        report = checklist_report(clean_draft(), persona)
        failing = [r["item"] for r in report if r["auto"] is False]
        assert failing == [], failing

    def test_missing_canonical_is_flagged(self, persona):
        report = checklist_report(clean_draft(canonical_url=""), persona)
        item = next(r for r in report if r["item"].startswith("Canonical URL"))
        assert item["auto"] is False

    def test_fewer_than_three_faq_is_flagged(self, persona):
        report = checklist_report(clean_draft(faq=[FAQItem("q", "a")]), persona)
        item = next(r for r in report if "FAQ answers" in r["item"])
        assert item["auto"] is False

    def test_short_meta_description_is_flagged(self, persona):
        report = checklist_report(clean_draft(meta_description="too short"), persona)
        item = next(r for r in report if "Meta description" in r["item"])
        assert item["auto"] is False

    def test_missing_disclosure_is_flagged(self, persona):
        report = checklist_report(clean_draft(body_markdown="plain body"), persona)
        item = next(r for r in report if "disclosure" in r["item"].lower())
        assert item["auto"] is False

    def test_edit_me_markers_fail_the_experience_item(self, persona):
        report = checklist_report(clean_draft(body_markdown=f"body {MARKER}"), persona)
        item = next(r for r in report if "experience" in r["item"].lower())
        assert item["auto"] is False

    def test_fact_checking_is_human_only(self, persona):
        report = checklist_report(clean_draft(), persona)
        item = next(r for r in report if "fact-checked" in r["item"].lower())
        assert item["auto"] is None and item["human_only"] is True

    def test_manual_tick_satisfies_a_human_only_item(self, persona):
        folder = None
        review = ReviewState(checklist={"Numbers/dates fact-checked against references (Trust)": True})
        report = checklist_report(clean_draft(), persona, review)
        item = next(r for r in report if "fact-checked" in r["item"].lower())
        assert item["done"] is True

    def test_works_without_a_persona(self):
        report = checklist_report(clean_draft(), None)
        item = next(r for r in report if "Author box" in r["item"])
        assert item["auto"] is None
        assert len(report) == 10


class TestProgress:
    def test_counts_done_items(self, persona):
        p = checklist_progress(checklist_report(clean_draft(), persona))
        assert p["total"] == 10
        assert 0 < p["done"] <= 10
        assert isinstance(p["complete"], bool)

    def test_complete_when_every_item_is_ticked(self, persona):
        report = checklist_report(clean_draft(), persona)
        for r in report:
            r["done"] = True
        assert checklist_progress(report)["complete"] is True

    def test_not_complete_when_one_is_outstanding(self, persona):
        report = checklist_report(clean_draft(), persona)
        report[0]["done"] = False
        assert checklist_progress(report)["complete"] is False


class TestPublishable:
    def test_pending_is_not_publishable(self, persona):
        assert is_publishable(clean_draft(), persona, ReviewState()) is False

    def test_approved_is_publishable(self, persona):
        assert is_publishable(clean_draft(), persona,
                              ReviewState(status=STATUS_APPROVED)) is True

    def test_rejected_is_not_publishable(self, persona):
        assert is_publishable(clean_draft(), persona,
                              ReviewState(status=STATUS_REJECTED)) is False

    def test_checklist_alone_does_not_unlock_publishing(self, persona):
        """ rubber-stamping the checklist must not bypass the human decision """
        report = checklist_report(clean_draft(), persona)
        review = ReviewState(checklist={r["item"]: True for r in report})
        assert is_publishable(clean_draft(), persona, review) is False

    def test_reads_state_from_disk(self, persona, folder):
        set_decision(folder, STATUS_APPROVED)
        assert is_publishable(clean_draft(), persona, load_review(folder)) is True


class TestDiscovery:
    def test_empty_when_no_drafts(self, tmp_path):
        assert iter_draft_folders(tmp_path) == []

    def test_finds_draft_folders_newest_first(self, tmp_path, persona):
        save_draft(clean_draft(slug="older"), persona, folder=tmp_path / "2026-01-01-older")
        save_draft(clean_draft(slug="newer"), persona, folder=tmp_path / "2026-02-01-newer")
        folders = iter_draft_folders(tmp_path)
        assert [f.name for f in folders] == ["2026-02-01-newer", "2026-01-01-older"]

    def test_folders_without_an_article_are_skipped(self, tmp_path, persona):
        save_draft(clean_draft(), persona, folder=tmp_path / "2026-01-01-good")
        (tmp_path / "2026-01-02-empty").mkdir()
        assert len(iter_draft_folders(tmp_path)) == 1

    def test_load_draft_folder_returns_none_when_missing(self, tmp_path):
        assert load_draft_folder(tmp_path / "nope") is None

    def test_unreadable_article_returns_none(self, tmp_path):
        f = tmp_path / "bad"; f.mkdir()
        (f / "article.md").write_text("no front matter here", encoding="utf-8")
        assert load_draft_folder(f) is None


class TestSummary:
    def test_reports_the_fields_the_ui_needs(self, tmp_path, persona):
        folder = save_draft(clean_draft(), persona, folder=tmp_path / "d")
        s = draft_summary(folder, clean_draft(), persona)
        for key in ("id", "title", "status", "words", "faq_count", "marker_count",
                    "checklist", "progress", "publishable", "canonical_url"):
            assert key in s

    def test_counts_words_and_markers(self, tmp_path, persona):
        d = clean_draft(body_markdown=f"one two three {MARKER}")
        s = draft_summary(tmp_path / "d", d, persona)
        assert s["words"] == len(d.body_markdown.split())
        assert s["marker_count"] == 1

    def test_picks_up_saved_review_state(self, tmp_path, persona):
        folder = tmp_path / "d"; folder.mkdir()
        set_decision(folder, STATUS_APPROVED)
        s = draft_summary(folder, clean_draft(), persona)
        assert s["status"] == STATUS_APPROVED and s["publishable"] is True

    def test_falls_back_to_folder_name_when_untitled(self, tmp_path, persona):
        s = draft_summary(tmp_path / "2026-01-01-x", ArticleDraft(), persona)
        assert s["title"] == "2026-01-01-x"


class TestTitleKeywordCheck:
    def test_title_containing_the_keyword_passes(self, persona):
        d = clean_draft(title="Canonical Url: A Practical Guide",
                        primary_keyword="canonical url")
        item = next(r for r in checklist_report(d, persona)
                    if r["item"].startswith("Title contains"))
        assert item["auto"] is True

    def test_title_without_the_keyword_is_flagged(self, persona):
        d = clean_draft(title="Some Other Topic Entirely",
                        primary_keyword="canonical url")
        item = next(r for r in checklist_report(d, persona)
                    if r["item"].startswith("Title contains"))
        assert item["auto"] is False

    def test_no_keyword_means_it_cannot_be_checked(self, persona):
        d = clean_draft(title="Anything", primary_keyword="")
        item = next(r for r in checklist_report(d, persona)
                    if r["item"].startswith("Title contains"))
        assert item["auto"] is False

"""Data models: markdown round-trip, tolerant loading, result rendering."""
from __future__ import annotations

import pytest

from autowebpost.models import (
    ArticleDraft,
    FAQItem,
    ImageAsset,
    Persona,
    PostResult,
    image_from_dict,
)


class TestDraftRoundTrip:
    def test_to_markdown_then_back_preserves_fields(self, draft):
        reloaded = ArticleDraft.from_markdown(draft.to_markdown())
        assert reloaded.title == draft.title
        assert reloaded.slug == draft.slug
        assert reloaded.meta_description == draft.meta_description
        assert reloaded.primary_keyword == draft.primary_keyword
        assert reloaded.secondary_keywords == draft.secondary_keywords
        assert reloaded.tags == draft.tags
        assert reloaded.references == draft.references
        assert reloaded.canonical_url == draft.canonical_url
        assert reloaded.language == draft.language
        assert reloaded.generator == draft.generator

    def test_faq_round_trips(self, draft):
        reloaded = ArticleDraft.from_markdown(draft.to_markdown())
        assert [(f.question, f.answer) for f in reloaded.faq] == [
            (f.question, f.answer) for f in draft.faq]

    def test_images_round_trip(self, draft):
        reloaded = ArticleDraft.from_markdown(draft.to_markdown())
        assert reloaded.images[0].path == draft.images[0].path
        assert reloaded.images[0].alt_text == draft.images[0].alt_text

    def test_body_is_preserved_after_front_matter(self, draft):
        reloaded = ArticleDraft.from_markdown(draft.to_markdown())
        assert reloaded.body_markdown.strip() == draft.body_markdown.strip()

    def test_load_reads_a_file(self, draft, tmp_path):
        p = tmp_path / "article.md"
        p.write_text(draft.to_markdown(), encoding="utf-8")
        assert ArticleDraft.load(p).title == draft.title

    def test_missing_front_matter_raises_clear_error(self):
        with pytest.raises(ValueError, match="front matter"):
            ArticleDraft.from_markdown("just a body, no front matter")

    def test_empty_front_matter_is_rejected_clearly(self):
        # a draft with no usable front matter is not publishable - say so
        with pytest.raises(ValueError, match="front matter"):
            ArticleDraft.from_markdown("---\n---\n\nbody")

    def test_front_matter_with_only_some_keys_yields_defaults(self):
        d = ArticleDraft.from_markdown("---\ntitle: Only Title\n---\n\nbody")
        assert d.title == "Only Title"
        assert d.tags == [] and d.faq == [] and d.language == "en"

    def test_accepts_q_a_aliases_for_faq(self):
        md = "---\nfaq:\n  - q: Why?\n    a: Because.\n---\n\nbody"
        d = ArticleDraft.from_markdown(md)
        assert d.faq == [FAQItem(question="Why?", answer="Because.")]


class TestImageFromDict:
    def test_keeps_known_fields(self):
        img = image_from_dict({"path": "images/a.jpg", "alt_text": "alt", "url": "https://x/y.jpg"})
        assert img.path == "images/a.jpg"
        assert img.alt_text == "alt"
        assert img.url == "https://x/y.jpg"

    def test_ignores_unknown_keys_instead_of_crashing(self):
        # Regression: a stray/renamed key used to raise TypeError and make the
        # entire draft unpublishable.
        img = image_from_dict({"path": "a.jpg", "seed": 42, "legacy_field": "x"})
        assert img.path == "a.jpg"

    def test_empty_dict_yields_defaults(self):
        assert image_from_dict({}).path == ""

    def test_draft_with_unknown_image_key_still_loads(self):
        md = (
            "---\n"
            "title: T\n"
            "images:\n"
            "- path: images/hero.jpg\n"
            "  seed: 99\n"
            "  legacy_field: x\n"
            "---\n\nbody\n"
        )
        assert ArticleDraft.from_markdown(md).images[0].path == "images/hero.jpg"


class TestPersona:
    def test_author_box_includes_name_and_credentials(self):
        p = Persona(name="Ada Lovelace", brand="Ada Labs", credentials=["MSc"],
                    social={"github": "https://github.com/ada"},
                    bio_long="Long bio.", experience_years=9)
        box = p.author_box_md()
        assert "Ada Lovelace" in box and "MSc" in box
        assert "https://github.com/ada" in box

    def test_author_box_falls_back_when_no_bio(self):
        p = Persona(name="Ada", brand="Ada Labs", tagline="Engineer")
        assert "Ada Labs" in p.author_box_md()


class TestPostResult:
    def test_dry_run_label(self):
        assert "[DRY-RUN]" in str(PostResult("devto", True, detail="payload", dry_run=True))

    def test_ok_shows_url(self):
        # "OK " is padded to align with the wider "DRY-RUN" label
        s = str(PostResult("devto", True, url="https://dev.to/x"))
        assert "[OK ]" in s and "https://dev.to/x" in s

    def test_failure_shows_detail(self):
        s = str(PostResult("devto", False, detail="missing env: DEVTO_API_KEY"))
        assert "[FAIL]" in s and "DEVTO_API_KEY" in s

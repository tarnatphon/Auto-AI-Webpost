"""Draft persistence: folder naming, sidecar files, structured-data bundle."""
from __future__ import annotations

import json
import re

from autowebpost.drafts import checklist_markdown, draft_folder, save_draft, seo_bundle


class TestDraftFolder:
    def test_prefixes_todays_date(self):
        folder = draft_folder("my-slug")
        assert folder.name.endswith("-my-slug")
        assert re.match(r"^\d{4}-\d{2}-\d{2}-my-slug$", folder.name)

    def test_honours_base_dir(self, tmp_path):
        assert draft_folder("s", base_dir=tmp_path) == tmp_path / f"{draft_folder('s').name}"

    def test_accepts_string_base_dir(self, tmp_path):
        assert draft_folder("s", base_dir=str(tmp_path)).parent == tmp_path


class TestSeoBundle:
    def test_always_emits_blogposting(self, draft, persona):
        bundle = seo_bundle(draft, persona)
        assert "BlogPosting" in bundle
        assert '"@context": "https://schema.org"' in bundle

    def test_emits_faqpage_when_draft_has_faq(self, draft, persona):
        assert "FAQPage" in seo_bundle(draft, persona)

    def test_omits_faqpage_when_no_faq(self, minimal_draft, persona):
        assert "FAQPage" not in seo_bundle(minimal_draft, persona)

    def test_every_block_is_valid_json(self, draft, persona):
        """Regression: the sidecar used to be a stub dict, not structured data."""
        bundle = seo_bundle(draft, persona)
        blocks = [b.strip() for b in re.split(r"^<!--.*?-->\s*$", bundle, flags=re.M) if b.strip()]
        assert blocks, "no JSON-LD documents emitted"
        types = {json.loads(b)["@type"] for b in blocks}
        assert types == {"BlogPosting", "FAQPage"}

    def test_uses_canonical_url_as_main_entity(self, draft, persona):
        blocks = [b for b in re.split(r"^<!--.*?-->\s*$", seo_bundle(draft, persona),
                                      flags=re.M) if b.strip()]
        ld = json.loads(blocks[0])
        assert ld["mainEntityOfPage"]["@id"] == draft.canonical_url


class TestChecklist:
    def test_is_a_markdown_task_list(self):
        md = checklist_markdown()
        assert md.startswith("# E-E-A-T review checklist")
        assert md.count("- [ ] ") >= 10

    def test_covers_the_core_signals(self):
        md = checklist_markdown().lower()
        for word in ("experience", "canonical", "references", "author"):
            assert word in md


class TestSaveDraft:
    def test_writes_article_and_sidecars(self, draft, persona, tmp_path):
        folder = save_draft(draft, persona, folder=tmp_path / "d")
        assert (folder / "article.md").exists()
        assert (folder / "seo.jsonld.txt").exists()
        assert (folder / "review-checklist.md").exists()

    def test_article_reloads_into_the_same_draft(self, draft, persona, tmp_path):
        from autowebpost.models import ArticleDraft
        folder = save_draft(draft, persona, folder=tmp_path / "d")
        assert ArticleDraft.load(folder / "article.md").title == draft.title

    def test_creates_the_folder_tree(self, draft, persona, tmp_path):
        folder = save_draft(draft, persona, folder=tmp_path / "a" / "b" / "c")
        assert folder.is_dir()

    def test_defaults_to_dated_folder(self, draft, persona, tmp_path, monkeypatch):
        import autowebpost.drafts as drafts_mod
        monkeypatch.setattr(drafts_mod, "OUTPUT_DIR", tmp_path)
        folder = save_draft(draft, persona)
        assert folder.parent == tmp_path / "drafts"
        assert folder.name.endswith(draft.slug)

    def test_overwriting_an_existing_draft_is_safe(self, draft, persona, tmp_path):
        folder = tmp_path / "d"
        save_draft(draft, persona, folder=folder)
        draft.title = "Retitled"
        save_draft(draft, persona, folder=folder)
        from autowebpost.models import ArticleDraft
        assert ArticleDraft.load(folder / "article.md").title == "Retitled"

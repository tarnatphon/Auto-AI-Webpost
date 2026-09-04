"""Content engine: brief -> draft, plus regressions for the FAQ/reference bugs."""
from __future__ import annotations

import re

import pytest

from autowebpost.content.engine import (
    Brief,
    LLMProvider,
    ContentEngine,
    TemplateProvider,
    _extract_faq,
    _extract_references,
    _parse_sections,
    make_provider,
)


@pytest.fixture
def engine(persona, template_provider):
    return ContentEngine(persona, template_provider)


def brief(**kw):
    base = dict(topic="Automating web publishing with AI",
                primary_keyword="AI auto posting workflow")
    base.update(kw)
    return Brief(**base)


class TestParseSections:
    def test_splits_all_markers(self):
        raw = "<<<TITLE>>>\nT\n<<<META>>>\nM\n<<<BODY>>>\nB\n<<<KEYWORDS>>>\nk1 | k2"
        parts = _parse_sections(raw)
        assert parts["TITLE"] == "T" and parts["META"] == "M"
        assert parts["BODY"] == "B" and parts["KEYWORDS"] == "k1 | k2"

    def test_unstructured_output_becomes_body(self):
        assert _parse_sections("just prose")["BODY"] == "just prose"


class TestExtractFaq:
    def test_pulls_questions_into_items(self):
        body = "## FAQ\n\n### What is it?\n\nAn answer.\n\n### Cost?\n\nFree.\n"
        _, faq = _extract_faq(body)
        assert [(f.question, f.answer) for f in faq] == [
            ("What is it?", "An answer."), ("Cost?", "Free.")]

    def test_no_faq_section_returns_empty(self):
        body, faq = _extract_faq("## Other\n\ntext")
        assert faq == [] and body == "## Other\n\ntext"

    def test_collapses_multiline_answers(self):
        _, faq = _extract_faq("## FAQ\n\n### Q?\n\nline one\nline two\n")
        assert faq[0].answer == "line one line two"

    def test_regression_faq_content_stays_in_body(self):
        """The Q&A used to be replaced by '<!-- faq-rendered-below -->', so every
        published copy shipped an empty FAQ section and lost the snippet content."""
        body = "## FAQ\n\n### What is it?\n\nAn answer.\n\n### Cost?\n\nFree.\n"
        new_body, faq = _extract_faq(body)
        assert "faq-rendered-below" not in new_body
        assert "### What is it?" in new_body
        assert "An answer." in new_body
        assert "### Cost?" in new_body
        assert "Free." in new_body
        assert len(faq) == 2

    def test_regression_questions_and_answers_survive_a_full_generate(self, engine):
        d = engine.generate(brief(), generate_images=False)
        for item in d.faq:
            assert item.question in d.body_markdown
            assert item.answer in d.body_markdown


class TestExtractReferences:
    def test_collects_numbered_refs(self):
        body, refs = _extract_references("## References\n\n1. https://a\n2. https://b\n")
        assert refs == ["https://a", "https://b"]

    def test_ignores_unfilled_edit_me_placeholders(self):
        """Placeholders are instructions to the author, not sources - and they
        used to shadow a real `--references` list."""
        body, refs = _extract_references(
            "## References\n\n1. <!-- EDIT-ME: primary source title + URL -->\n")
        assert refs == []

    def test_no_section_returns_empty(self):
        body, refs = _extract_references("no refs here")
        assert refs == [] and body == "no refs here"


class TestTemplateProvider:
    def test_emits_every_marker(self, template_provider):
        out = template_provider.complete("system", "TOPIC: My Topic\nPRIMARY KEYWORD: my keyword")
        for marker in ("<<<TITLE>>>", "<<<META>>>", "<<<TAGS>>>", "<<<BODY>>>", "<<<KEYWORDS>>>"):
            assert marker in out

    def test_uses_keyword_not_topic(self, template_provider):
        out = template_provider.complete("s", "TOPIC: My Topic\nPRIMARY KEYWORD: my keyword")
        assert "my keyword".title() in out or "My Keyword" in out

    def test_falls_back_to_topic_without_keyword(self, template_provider):
        out = template_provider.complete("s", "TOPIC: Only Topic Here")
        assert "Only Topic Here".lower() in out.lower()

    def test_regression_empty_keyword_does_not_yield_none(self, template_provider):
        """`m and mk and mk.group(1) or topic` degraded badly on falsy parses."""
        out = template_provider.complete("s", "TOPIC: Fallback Topic\nPRIMARY KEYWORD:    ")
        assert "None" not in out


class TestGenerate:
    def test_produces_a_publishable_draft(self, engine):
        d = engine.generate(brief(), generate_images=False)
        assert d.title and d.slug and d.meta_description
        assert d.body_markdown
        assert d.generator == "template"

    def test_slug_is_url_safe(self, engine):
        d = engine.generate(brief(), generate_images=False)
        assert re.fullmatch(r"[a-z0-9-]+", d.slug)

    def test_tags_are_limited_and_clean(self, engine):
        d = engine.generate(brief(), generate_images=False)
        assert 0 < len(d.tags) <= 4
        assert all(re.fullmatch(r"[a-z0-9]+", t) for t in d.tags)

    def test_meta_description_is_reasonable_length(self, engine):
        d = engine.generate(brief(), generate_images=False)
        assert 100 < len(d.meta_description) < 175

    def test_e_e_a_t_blocks_present(self, engine, persona):
        d = engine.generate(brief(), generate_images=False)
        assert persona.name in d.body_markdown       # author box
        assert "Editorial note" in d.body_markdown   # disclosure
        assert persona.brand in d.body_markdown      # trust block

    def test_faq_extracted(self, engine):
        assert len(engine.generate(brief(), generate_images=False).faq) == 3

    def test_supplied_references_win_over_placeholders(self, engine):
        """Regression: `--references` was silently discarded because the template's
        unfilled EDIT-ME markers counted as 'references already present'."""
        refs = ["https://example.com/a", "https://example.com/b"]
        d = engine.generate(brief(references=refs), generate_images=False)
        assert d.references == refs

    def test_supplied_references_are_rendered_into_body(self, engine):
        d = engine.generate(brief(references=["https://example.com/a"]),
                            generate_images=False)
        assert "https://example.com/a" in d.body_markdown

    def test_no_references_when_none_supplied(self, engine):
        d = engine.generate(brief(), generate_images=False)
        assert d.references == []


class TestProviderFallback:
    class ExplodingProvider(LLMProvider):
        """Not a TemplateProvider: the engine deliberately re-raises template
        failures, so the fallback test needs a provider that is allowed to fall
        back."""
        name = "exploding"

        def complete(self, system, user):
            raise RuntimeError("network is down")

    def test_falls_back_to_template_and_flags_it(self, persona):
        eng = ContentEngine(persona, self.ExplodingProvider())
        d = eng.generate(brief(), generate_images=False)
        assert eng.fallback_used is True
        assert d.generator == "template"
        assert d.body_markdown

    def test_template_failure_is_not_swallowed(self, persona):
        class BrokenTemplate(TemplateProvider):
            def complete(self, system, user):
                raise RuntimeError("template broken")

        with pytest.raises(RuntimeError, match="template broken"):
            ContentEngine(persona, BrokenTemplate()).generate(brief(), generate_images=False)

    def test_make_provider_defaults_to_template(self):
        assert isinstance(make_provider({}), TemplateProvider)

    def test_make_provider_template_explicit(self):
        assert isinstance(make_provider({"provider": "template"}), TemplateProvider)

    def test_make_provider_pollinations(self):
        assert make_provider({"provider": "pollinations"}).name == "pollinations"

    def test_env_var_overrides_the_config_file(self, monkeypatch):
        """AUTOWEBPOST_PROVIDER lets CI (and one-off runs) force offline mode."""
        monkeypatch.setenv("AUTOWEBPOST_PROVIDER", "template")
        assert isinstance(make_provider({"provider": "pollinations"}), TemplateProvider)

    def test_env_var_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("AUTOWEBPOST_PROVIDER", "TEMPLATE")
        assert isinstance(make_provider({"provider": "pollinations"}), TemplateProvider)

    def test_make_provider_openai_requires_a_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            make_provider({"provider": "openai"})


class TestAttachImages:
    def test_images_land_in_the_draft_folder_with_relative_paths(self, engine, tmp_path):
        """Regression: images were written to output/drafts/<slug>/images while the
        article went to output/drafts/<date>-<slug>/, so every image link broke."""
        import autowebpost.images.provider as images_mod

        calls = []

        def fake_images_for_draft(draft, max_images=2, draft_dir=None):
            calls.append(draft_dir)
            folder = (draft_dir or tmp_path) / "images"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "hero.jpg").write_bytes(b"x")
            from autowebpost.models import ImageAsset
            return [ImageAsset(path=f"images/hero.jpg", alt_text="hero")]

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(images_mod, "images_for_draft", fake_images_for_draft)
        try:
            d = engine.generate(brief(), generate_images=False)
            d.body_markdown += "\n[IMAGE: hero]\n"
            engine.attach_images(d, tmp_path)
        finally:
            monkeypatch.undo()

        assert calls == [tmp_path]
        assert (tmp_path / "images" / "hero.jpg").exists()
        assert d.images[0].path == "images/hero.jpg"  # portable, not absolute
        assert "images/hero.jpg" in d.body_markdown

    def test_image_failure_never_breaks_the_draft(self, engine, tmp_path):
        import autowebpost.images.provider as images_mod

        monkeypatch = pytest.MonkeyPatch()
        def boom(*a, **k):
            raise RuntimeError("boom")
        monkeypatch.setattr(images_mod, "images_for_draft", boom)
        try:
            d = engine.attach_images(engine.generate(brief(), generate_images=False), tmp_path)
        finally:
            monkeypatch.undo()
        assert d.images == [] and d.body_markdown

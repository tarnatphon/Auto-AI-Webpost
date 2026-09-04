"""SEO helpers: slugs, meta descriptions, tags, structured data."""
from __future__ import annotations

import json

import pytest

from autowebpost.content.seo import (
    build_meta_description,
    clean_tag,
    extract_keywords,
    json_ld_article,
    json_ld_faq,
    slugify,
    smart_title,
)


class TestSlugify:
    def test_basic(self):
        assert slugify("AI Auto Posting Workflow: The Practical 2026 Guide") == (
            "ai-auto-posting-workflow-the-practical-2026-guide")

    def test_strips_punctuation_and_accents(self):
        assert slugify("Café — Naïve Résumé!") == "cafe-naive-resume"

    def test_collapses_separators(self):
        # non-alphanumerics are stripped first, then runs of separators collapse
        assert slugify("multiple   spaces  and--dashes") == "multiple-spaces-and-dashes"

    def test_no_leading_trailing_dashes(self):
        assert slugify("--- hello world ---") == "hello-world"

    @pytest.mark.parametrize("text", ["", "!!!", "   "])
    def test_degenerate_input_returns_empty_not_crash(self, text):
        assert slugify(text) == ""

    def test_respects_max_len_at_word_boundary(self):
        slug = slugify("word " * 60, max_len=20)
        assert len(slug) <= 20
        assert not slug.endswith("-")


class TestSmartTitle:
    def test_uppercases_known_acronyms(self):
        assert smart_title("ai seo workflow") == "AI SEO Workflow"

    def test_leaves_ordinary_words_alone(self):
        assert smart_title("practical guide") == "Practical Guide"

    def test_preserves_existing_caps_of_unknown_words(self):
        assert smart_title("GitHub pages") == "GitHub Pages"


class TestMetaDescription:
    def test_prefers_a_sentence_boundary_in_the_sweet_spot(self):
        # boundary must land between 60 and 158 chars to be used
        # boundary sits at index 75: inside the 60..158 window, so it is used
        first = "A reasonably long opening clause that definitely runs past sixty characters. "
        assert 60 < first.find(". ") < 158
        out = build_meta_description(first + "x" * 300, "keyword")
        assert out == first.strip()
        assert not out.endswith("\u2026")

    def test_ignores_a_boundary_that_is_too_early(self):
        # boundary at index 9: outside the window, so it falls through to truncation
        out = build_meta_description("Too short. " + "y" * 300, "keyword")
        assert out.endswith("\u2026")
        assert len(out) <= 160

    def test_truncates_long_single_sentence(self):
        out = build_meta_description("no sentence end here " * 40, "kw")
        assert len(out) <= 160

    def test_falls_back_when_empty(self):
        out = build_meta_description("", "my keyword")
        assert "my keyword" in out

    def test_collapses_whitespace(self):
        assert build_meta_description("a\n\n  b\t c") == "a b c"


class TestCleanTag:
    def test_lowercases_and_strips_symbols(self):
        assert clean_tag("AI Auto-Posting!") == "aiautoposting"

    @pytest.mark.parametrize("raw,expected", [("AI", "ai"), ("a" * 40, "a" * 24)])
    def test_length_and_case(self, raw, expected):
        assert clean_tag(raw) == expected


class TestExtractKeywords:
    def test_drops_stopwords_and_short_words(self):
        kws = extract_keywords("the workflow is automated and the workflow runs daily", 5)
        assert "the" not in kws and "and" not in kws
        assert kws[0] == "workflow"  # highest frequency

    def test_respects_top(self):
        assert len(extract_keywords("alpha beta gamma delta epsilon zeta", top=3)) == 3


class TestJsonLd:
    def test_article_is_valid_json_with_required_fields(self, draft, persona):
        ld = json.loads(json_ld_article(draft, persona, url=draft.canonical_url))
        assert ld["@context"] == "https://schema.org"
        assert ld["@type"] == "BlogPosting"
        assert ld["headline"] == draft.title
        assert ld["author"]["name"] == persona.name
        assert ld["mainEntityOfPage"]["@id"] == draft.canonical_url
        assert ld["keywords"].startswith(draft.primary_keyword)

    def test_article_omits_url_fields_when_unknown(self, draft, persona):
        ld = json.loads(json_ld_article(draft, persona))
        assert "mainEntityOfPage" not in ld

    def test_headline_is_capped_for_schema(self, draft, persona):
        draft.title = "X" * 400
        ld = json.loads(json_ld_article(draft, persona))
        assert len(ld["headline"]) <= 110

    def test_faq_is_valid_json_and_mirrors_items(self, draft):
        ld = json.loads(json_ld_faq(draft))
        assert ld["@type"] == "FAQPage"
        assert len(ld["mainEntity"]) == len(draft.faq)
        assert ld["mainEntity"][0]["name"] == draft.faq[0].question
        assert ld["mainEntity"][0]["acceptedAnswer"]["text"] == draft.faq[0].answer

    def test_faq_returns_empty_string_when_no_faq(self, minimal_draft):
        assert json_ld_faq(minimal_draft) == ""

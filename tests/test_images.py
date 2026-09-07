"""AI image generation (Pollinations), HTTP mocked."""
from __future__ import annotations

import pytest
import requests

from autowebpost.images.provider import build_prompt, generate_image, images_for_draft
from autowebpost.models import ArticleDraft


class FakeResponse:
    def __init__(self, content=b"", status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("boom", response=self)


JPEG = b"\xff\xd8\xff\xe0" + b"0" * 9000  # plausible image payload


class TestBuildPrompt:
    def test_includes_the_topic(self):
        assert "workflow" in build_prompt("my workflow")

    def test_varies_by_style_index(self):
        assert build_prompt("t", 0) != build_prompt("t", 1)

    def test_cycles_back_around(self):
        from autowebpost.content import prompts
        assert build_prompt("t", 0) == build_prompt("t", len(prompts.STYLE_HINTS))


class TestGenerateImage:
    def test_writes_the_downloaded_bytes(self, monkeypatch, tmp_path):
        seen = {}

        def _get(url, **kw):
            seen["url"] = url
            return FakeResponse(JPEG)
        monkeypatch.setattr(requests, "get", _get)

        out = tmp_path / "sub" / "hero.jpg"
        result = generate_image("a diagram of a workflow", out)

        assert out.exists() and out.read_bytes() == JPEG
        assert str(out) == result
        assert "image.pollinations.ai/prompt" in seen["url"]
        assert "width=1200" in seen["url"] and "height=675" in seen["url"]

    def test_creates_parent_directories(self, monkeypatch, tmp_path):
        monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(JPEG))
        out = tmp_path / "a" / "b" / "c" / "hero.jpg"
        generate_image("p", out)
        assert out.exists()

    def test_rejects_an_error_page_disguised_as_an_image(self, monkeypatch, tmp_path):
        """A tiny response means we got an error page, not an image."""
        monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(b"<html>err</html>"))
        with pytest.raises(RuntimeError, match="too small"):
            generate_image("p", tmp_path / "hero.jpg")

    def test_http_errors_propagate(self, monkeypatch, tmp_path):
        monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(b"", status=500))
        with pytest.raises(requests.HTTPError):
            generate_image("p", tmp_path / "hero.jpg")

    def test_seed_is_derived_from_the_prompt(self, monkeypatch, tmp_path):
        urls = []
        monkeypatch.setattr(requests, "get",
                            lambda url, **kw: (urls.append(url), FakeResponse(JPEG))[1])
        generate_image("same prompt", tmp_path / "a.jpg")
        generate_image("same prompt", tmp_path / "b.jpg")
        assert "seed=" in urls[0] and urls[0] == urls[1]  # deterministic


class TestImagesForDraft:
    def test_writes_into_the_draft_folder(self, monkeypatch, tmp_path):
        """Regression: images went to output/drafts/<slug>/images while the article
        lived in output/drafts/<date>-<slug>/, so every image link was broken."""
        monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(JPEG))
        draft = ArticleDraft(title="T", slug="t", primary_keyword="kw",
                             body_markdown="intro\n\n[IMAGE: a diagram of the flow]\n")

        assets = images_for_draft(draft, draft_dir=tmp_path)

        assert assets
        assert (tmp_path / "images" / "t-hero.jpg").exists()
        assert assets[0].path == "images/t-hero.jpg"   # relative => portable

    def test_uses_the_image_placeholder_as_alt_text(self, monkeypatch, tmp_path):
        monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(JPEG))
        draft = ArticleDraft(title="T", slug="t", primary_keyword="kw",
                             body_markdown="[IMAGE: workflow overview diagram]")
        assets = images_for_draft(draft, draft_dir=tmp_path)
        assert assets[0].alt_text == "workflow overview diagram"

    def test_falls_back_to_a_descriptive_alt_text(self, monkeypatch, tmp_path):
        monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(JPEG))
        draft = ArticleDraft(title="My Title", slug="t", primary_keyword="kw",
                             body_markdown="no placeholders here")
        assets = images_for_draft(draft, draft_dir=tmp_path)
        assert "My Title" in assets[0].alt_text

    def test_respects_max_images(self, monkeypatch, tmp_path):
        monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(JPEG))
        body = "\n".join(f"[IMAGE: alt {i}]" for i in range(6))
        draft = ArticleDraft(title="T", slug="t", primary_keyword="kw", body_markdown=body)
        assert len(images_for_draft(draft, max_images=2, draft_dir=tmp_path)) == 2

    def test_a_failed_image_is_skipped_not_fatal(self, monkeypatch, tmp_path):
        monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(b"", status=500))
        draft = ArticleDraft(title="T", slug="t", primary_keyword="kw",
                             body_markdown="[IMAGE: alt]")
        assert images_for_draft(draft, draft_dir=tmp_path) == []

    def test_defaults_to_the_output_tree_without_a_draft_dir(self, monkeypatch, tmp_path):
        import autowebpost.images.provider as provider_mod
        monkeypatch.setattr(provider_mod, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(JPEG))
        draft = ArticleDraft(title="T", slug="t", primary_keyword="kw",
                             body_markdown="[IMAGE: alt]")
        assets = images_for_draft(draft)
        assert assets[0].path == "images/t-hero.jpg"
        assert (tmp_path / "drafts" / "t" / "images" / "t-hero.jpg").exists()

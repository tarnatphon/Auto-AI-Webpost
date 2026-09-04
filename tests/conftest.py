"""Shared fixtures.

Every fixture is offline: no network, no API keys, no real publishing. Tests
that touch network-dependent code inject a fake instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from autowebpost.models import ArticleDraft, FAQItem, ImageAsset, Persona  # noqa: E402
from autowebpost.profiles.persona import load_persona  # noqa: E402


@pytest.fixture
def persona() -> Persona:
    """The bundled example persona (no network, no user data)."""
    return load_persona()


@pytest.fixture
def draft() -> ArticleDraft:
    """A realistic draft: FAQ, references, one image, canonical URL."""
    return ArticleDraft(
        title="AI Auto Posting Workflow: The Practical 2026 Guide",
        slug="ai-auto-posting-workflow-the-practical-2026-guide",
        meta_description="A field-tested guide to AI auto posting workflows - steps, tools, "
                         "mistakes to avoid, and a checklist you can apply today.",
        primary_keyword="AI auto posting workflow",
        secondary_keywords=["content automation", "canonical url"],
        tags=["aiautopostingworkflow", "guide", "automation"],
        body_markdown=(
            "Few decisions move the needle on **AI auto posting workflow** as much as\n"
            "having a repeatable system.\n\n"
            "## Key takeaways\n\n"
            "- Takeaway one\n"
            "- Takeaway two\n\n"
            "## Step-by-step\n\n"
            "1. Generate\n"
            "2. Review\n"
            "3. Publish\n\n"
            "## FAQ\n\n"
            "### What is AI auto posting workflow?\n\n"
            "A repeatable pipeline that takes one article to many platforms.\n\n"
            "### Is it free to start?\n\n"
            "Yes, every platform in the catalog has a free tier.\n"
        ),
        faq=[
            FAQItem(question="What is AI auto posting workflow?",
                    answer="A repeatable pipeline that takes one article to many platforms."),
            FAQItem(question="Is it free to start?",
                    answer="Yes, every platform in the catalog has a free tier."),
        ],
        references=["https://example.com/primary-source"],
        images=[ImageAsset(path="images/hero.jpg", prompt="a diagram",
                           alt_text="Workflow overview diagram")],
        canonical_url="https://yourname.github.io/ai-auto-posting-workflow.html",
        generator="template",
    )


@pytest.fixture
def minimal_draft() -> ArticleDraft:
    return ArticleDraft(title="Untitled Draft", slug="untitled-draft",
                        body_markdown="Body text.")


@pytest.fixture
def template_provider():
    from autowebpost.content.engine import TemplateProvider
    return TemplateProvider()

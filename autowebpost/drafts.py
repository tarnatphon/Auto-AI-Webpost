"""Draft persistence: where an article + its sidecars live on disk.

One folder per draft, and *everything* that belongs to the article goes in it:

    output/drafts/<date>-<slug>/
        article.md            front matter + body (the thing you publish)
        seo.jsonld.txt        real BlogPosting (+ FAQPage) structured data
        review-checklist.md   the E-E-A-T gate, tick before you publish
        images/               generated hero/inline images

The folder is created before images are generated so that images land beside
the article they belong to (previously images were written to a folder without
the date prefix, so every image reference was broken).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .config import OUTPUT_DIR, utc_today_iso
from .content.eeat import eeat_qa_checklist
from .content.seo import json_ld_article, json_ld_faq
from .models import ArticleDraft, Persona

# EDIT-ME placeholders are instructions to the human, never published content.
CHECKLIST_HEADER = "# E-E-A-T review checklist (do this BEFORE publishing)\n\n"


def draft_folder(slug: str, base_dir: Optional[Union[str, Path]] = None) -> Path:
    """Deterministic folder for a draft: <base>/<today>-<slug>."""
    base = Path(base_dir) if base_dir else (OUTPUT_DIR / "drafts")
    return base / f"{utc_today_iso()}-{slug}"


def seo_bundle(draft: ArticleDraft, persona: Persona) -> str:
    """Structured data for the article, ready to paste into a <script> tag.

    Emits one JSON-LD document per schema type, each under a comment saying
    where it goes. Google accepts multiple ld+json blocks on a page, and
    keeping BlogPosting and FAQPage separate makes them easy to paste
    selectively (FAQPage must match visible FAQ content to be eligible).
    """
    blocks = [("BlogPosting", json_ld_article(draft, persona, url=draft.canonical_url))]
    faq = json_ld_faq(draft)
    if faq:
        blocks.append(("FAQPage", faq))

    out: list = []
    for kind, doc in blocks:
        out.append(f"<!-- {kind}: paste inside "
                   f'<script type="application/ld+json"> ... </script> -->')
        out.append(doc)
        out.append("")
    return "\n".join(out)


def checklist_markdown() -> str:
    return CHECKLIST_HEADER + "\n".join(f"- [ ] {c}" for c in eeat_qa_checklist()) + "\n"


def save_draft(draft: ArticleDraft, persona: Persona,
               folder: Optional[Union[str, Path]] = None,
               base_dir: Optional[Union[str, Path]] = None) -> Path:
    """Write article.md + sidecars into the draft folder and return the folder."""
    folder = Path(folder) if folder else draft_folder(draft.slug, base_dir)
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "article.md").write_text(draft.to_markdown(), encoding="utf-8")
    (folder / "seo.jsonld.txt").write_text(seo_bundle(draft, persona), encoding="utf-8")
    (folder / "review-checklist.md").write_text(checklist_markdown(), encoding="utf-8")
    return folder

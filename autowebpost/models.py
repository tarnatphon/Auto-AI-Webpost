"""Core data models."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import yaml


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Persona:
    """The single, consistent identity used across every platform.

    This is *your* identity (real or pen-name brand). It powers E-E-A-T author
    boxes, profile pre-fill data, and consistent entity signals for SEO.
    """

    name: str = "Jane Doe"
    handle: str = "janedoe"
    brand: str = "Jane Writes"
    email: str = ""
    website: str = ""
    tagline: str = ""
    expertise: List[str] = field(default_factory=list)
    credentials: List[str] = field(default_factory=list)
    experience_years: int = 5
    bio_short: str = ""
    bio_long: str = ""
    social: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path) -> "Persona":
        with open(path, "r", encoding="utf-8") as fh:
            return cls(**yaml.safe_load(fh))

    def save(self, path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(asdict(self), fh, sort_keys=False, allow_unicode=True)

    def author_box_md(self) -> str:
        creds = " ".join(f"`{c}`" for c in self.credentials[:4])
        socials = " | ".join(f"[{k}]({v})" for k, v in self.social.items() if v)
        lines = [
            f"**About the author — {self.name}**",
            "",
            self.bio_long or self.bio_short or f"{self.brand}. {self.tagline}",
            "",
        ]
        if creds:
            lines += [f"*Credentials:* {creds}", ""]
        if socials:
            lines += [f"*Find me:* {socials}", ""]
        return "\n".join(lines)


@dataclass
class FAQItem:
    question: str
    answer: str


@dataclass
class ImageAsset:
    path: str = ""
    prompt: str = ""
    alt_text: str = ""
    credit: str = "Image: AI-generated (Flux via Pollinations.ai)"
    url: str = ""  # remote URL once uploaded / published


@dataclass
class ArticleDraft:
    title: str = ""
    slug: str = ""
    meta_description: str = ""
    primary_keyword: str = ""
    secondary_keywords: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    body_markdown: str = ""
    faq: List[FAQItem] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    images: List[ImageAsset] = field(default_factory=list)
    canonical_url: str = ""
    language: str = "en"
    created_at: str = field(default_factory=_now_iso)
    generator: str = "template"

    # ---------- persistence ----------
    def to_markdown(self) -> str:
        fm = {
            "title": self.title,
            "slug": self.slug,
            "meta_description": self.meta_description,
            "primary_keyword": self.primary_keyword,
            "secondary_keywords": self.secondary_keywords,
            "tags": self.tags,
            "faq": [{"q": f.question, "a": f.answer} for f in self.faq],
            "references": self.references,
            "images": [asdict(i) for i in self.images],
            "canonical_url": self.canonical_url,
            "language": self.language,
            "created_at": self.created_at,
            "generator": self.generator,
        }
        return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n" + self.body_markdown

    @classmethod
    def from_markdown(cls, text: str) -> "ArticleDraft":
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
        if not m:
            raise ValueError("Draft file missing YAML front matter")
        fm = yaml.safe_load(m.group(1)) or {}
        d = cls()
        d.title = fm.get("title", "")
        d.slug = fm.get("slug", "")
        d.meta_description = fm.get("meta_description", "")
        d.primary_keyword = fm.get("primary_keyword", "")
        d.secondary_keywords = fm.get("secondary_keywords") or []
        d.tags = fm.get("tags") or []
        d.faq = [
            FAQItem(question=(i.get("question") or i.get("q", "")), answer=(i.get("answer") or i.get("a", "")))
            for i in (fm.get("faq") or [])
        ]
        d.references = fm.get("references") or []
        d.images = [ImageAsset(**i) for i in (fm.get("images") or [])]
        d.canonical_url = fm.get("canonical_url", "")
        d.language = fm.get("language", "en")
        d.created_at = fm.get("created_at", _now_iso())
        d.generator = fm.get("generator", "unknown")
        d.body_markdown = m.group(2)
        return d

    @classmethod
    def load(cls, path) -> "ArticleDraft":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_markdown(fh.read())


@dataclass
class PostResult:
    platform: str
    ok: bool
    url: str = ""
    detail: str = ""
    dry_run: bool = False
    at: str = field(default_factory=_now_iso)

    def __str__(self) -> str:
        flag = "DRY-RUN" if self.dry_run else ("OK " if self.ok else "FAIL")
        return f"[{flag}] {self.platform}: {self.detail or self.url or 'no detail'}" + (f" -> {self.url}" if self.url and self.detail else "")

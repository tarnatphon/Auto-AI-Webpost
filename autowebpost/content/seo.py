"""SEO helpers: slugs, meta descriptions, structured data (JSON-LD)."""
from __future__ import annotations

import json
import re
import unicodedata
from typing import List

from ..models import ArticleDraft, Persona

_STOP = set("""a an and are as at be but by for from has have how i in is it its of on or that the this to was what when where which who will with you your our we""".split())


def slugify(text: str, max_len: int = 72) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text).lower().strip()
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    while len(text) > max_len:
        text = "-".join(text.split("-")[:-1])
    return text


def smart_title(text: str) -> str:
    """Title-case that keeps common tech acronyms uppercase."""
    acronyms = {"ai", "seo", "api", "ui", "ux", "saas", "eeat", "llm", "crm", "kpi", "cms", "rss"}
    words = []
    for w in text.split():
        wl = w.strip(":-,.").lower()
        if wl in acronyms:
            words.append(w.replace(wl, wl.upper()))
        else:
            words.append(w[0].upper() + w[1:] if w else w)
    return " ".join(words)


def build_meta_description(summary: str, keyword: str = "", max_len: int = 158) -> str:
    s = re.sub(r"\s+", " ", summary).strip()
    if not s:
        s = f"Practical guide covering {keyword}." if keyword else "Practical guide."
    s = s[: max_len + 40]
    # prefer cutting at a sentence boundary
    for sep in [". ", "! ", "? "]:
        idx = s.find(sep)
        if 60 < idx < max_len + len(sep):
            return s[: idx + 1].strip()
    if len(s) > max_len:
        cut = s[:max_len]
        s = cut[: cut.rfind(" ")].rstrip(",;:-") + "…"
    return s


def clean_tag(t: str) -> str:
    t = re.sub(r"[^a-z0-9]", "", t.lower())
    return t[:24]


def extract_keywords(text: str, top: int = 8) -> List[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", text.lower())
    freq: dict = {}
    for w in words:
        if w in _STOP:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:top]]


def json_ld_article(draft: ArticleDraft, persona: Persona, url: str = "") -> str:
    ld = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": draft.title[:110],
        "description": draft.meta_description,
        "inLanguage": draft.language,
        "keywords": ", ".join([draft.primary_keyword] + draft.secondary_keywords[:6]),
        "datePublished": draft.created_at,
        "dateModified": draft.created_at,
        "author": {
            "@type": "Person",
            "name": persona.name,
            "url": persona.website or None,
            "jobTitle": persona.tagline or None,
            "knowsAbout": persona.expertise[:6],
        },
        "publisher": {"@type": "Organization", "name": persona.brand},
    }
    if url:
        ld["mainEntityOfPage"] = {"@type": "WebPage", "@id": url}
    if draft.images:
        ld["image"] = [i.url or i.path for i in draft.images]
    return json.dumps(ld, ensure_ascii=False, indent=2)


def json_ld_faq(draft: ArticleDraft) -> str:
    if not draft.faq:
        return ""
    ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f.question, "acceptedAnswer": {"@type": "Answer", "text": f.answer}}
            for f in draft.faq
        ],
    }
    return json.dumps(ld, ensure_ascii=False, indent=2)

"""Content engine: turns a brief into a full SEO/E-E-A-T article draft.

Providers (pick per-run, configured in data/config.yaml -> content.provider):
  * pollinations  - FREE, no API key (https://text.pollinations.ai), rate-limited
  * openai        - any OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, Ollama, LM Studio)
  * template      - deterministic offline scaffold; you fill the meat (always works)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

import requests

from ..models import ArticleDraft, FAQItem, ImageAsset, Persona
from . import prompts
from .eeat import author_box, disclosure_block, references_section, trust_block
from .seo import build_meta_description, clean_tag, extract_keywords, slugify

UA = {"User-Agent": "AutoAIWebPost/0.1 (https://github.com/)"}

# Unfilled template markers: instructions to the author, never published content.
_PLACEHOLDER = re.compile(r"<!--\s*EDIT-ME.*?-->", re.I | re.S)


@dataclass
class Brief:
    topic: str
    primary_keyword: str = ""
    secondary_keywords: List[str] = field(default_factory=list)
    angle: str = "practical, experience-based how-to"
    audience: str = "intermediate practitioners looking for actionable steps"
    tone: str = "expert-friendly, direct, concrete"
    word_target: int = 1400
    references: List[str] = field(default_factory=list)
    # filled from persona by engine if empty
    author_name: str = ""
    author_tagline: str = ""
    author_experience_years: int = 0
    author_expertise: List[str] = field(default_factory=list)


class LLMProvider:
    name = "base"

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


class OpenAICompatProvider(LLMProvider):
    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 180):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        r = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", **UA},
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0.7,
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


class PollinationsProvider(LLMProvider):
    """Free, keyless, OpenAI-shaped text endpoint."""
    name = "pollinations"

    def __init__(self, model: str = "openai", timeout: int = 240):
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.7,
        }
        try:
            r = requests.post("https://text.pollinations.ai/openai", json=payload, headers=UA, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            # fallback: simple GET endpoint
            q = requests.utils.quote(f"{system}\n\n{user}"[:6000])
            r = requests.get(f"https://text.pollinations.ai/{q}?model={self.model}", headers=UA, timeout=self.timeout)
            r.raise_for_status()
            return r.text


class GeminiNativeProvider(LLMProvider):
    """Google Gemini through the native generativelanguage API (has a free tier).

    Separate from the OpenAI-compatible provider because Gemini's own endpoint
    takes a different request shape (system_instruction + contents/parts) and
    its own auth header.

        GEMINI_API_KEY=...      (aistudio.google.com/apikey)
    """
    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", timeout: int = 240):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.7},
        }
        url = f"{self.BASE}/{self.model}:generateContent"
        last = "no attempt made"

        # The key is accepted either as a header or as a query parameter; which
        # one works depends on the endpoint version, so try both.
        for transport in ("header", "query"):
            try:
                if transport == "header":
                    r = requests.post(url, headers={"x-goog-api-key": self.api_key, **UA},
                                      json=body, timeout=self.timeout)
                else:
                    r = requests.post(url + "?key=" + self.api_key, headers=UA,
                                      json=body, timeout=self.timeout)
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
                continue

            if not r.ok:
                last = f"HTTP {r.status_code}: {r.text[:200]}"
                continue

            candidates = r.json().get("candidates") or []
            if not candidates:
                last = "empty candidates"
                continue
            text = "".join(p.get("text", "")
                           for p in (candidates[0].get("content") or {}).get("parts", []))
            if text:
                return text
            last = "empty candidates"

        raise RuntimeError(f"Gemini native ({self.model}) failed: {last}")


class TemplateProvider(LLMProvider):
    """Deterministic scaffold - the structure is done, you add the specifics.
    Guaranteed to work offline; also the best prompt for a human writer."""

    name = "template"

    def complete(self, system: str, user: str) -> str:
        m = re.search(r"TOPIC: (.+)", user)
        topic = m.group(1).strip() if m else "Your Topic"
        mk = re.search(r"PRIMARY KEYWORD: (.+)", user)
        # Explicit fallback chain - the old `a and b and c or d` chained truthiness
        # returned `topic` whenever the keyword parsed to a falsy value.
        kw = (mk.group(1).strip() if mk else "") or topic
        wc = 0
        from .seo import smart_title
        return f"""<<<TITLE>>>
{smart_title(kw)}: The Practical 2026 Guide
<<<META>>>
A field-tested guide to {kw.lower()} - steps, tools, mistakes to avoid, and a checklist you can apply today.
<<<TAGS>>>
{clean_tag(kw)}, guide, tutorial, automation
<<<BODY>>>
Few decisions move the needle on **{kw.lower()}** as much as having a repeatable system. <!-- EDIT-ME: open with YOUR concrete experience hook in 2-3 sentences. -->

## Key takeaways

- <!-- EDIT-ME: takeaway 1 - the single most important fact about {kw.lower()} -->
- <!-- EDIT-ME: takeaway 2 - what most people get wrong -->
- <!-- EDIT-ME: takeaway 3 - the fastest first step -->

[IMAGE: {kw.lower()} workflow overview diagram]

## Why {kw.title()} matters in 2026

<!-- EDIT-ME: 2 paragraphs. Cite primary sources [1][2] for every statistic. -->

## How {kw.title()} works: the core workflow

<!-- EDIT-ME: explain the mechanism step by step. -->

| Approach | Effort | Speed | Best for |
|---|---|---|---|
| Manual | High | Slow | <!-- one-off --> |
| Semi-automated | Medium | Medium | <!-- growing teams --> |
| Fully automated | Low to run | Fast | <!-- scale, with review --> |

## Step-by-step: your first run

1. <!-- EDIT-ME: step 1 - concrete action, tool, expected result -->
2. <!-- EDIT-ME: step 2 -->
3. <!-- EDIT-ME: step 3 -->
4. <!-- EDIT-ME: verify and publish -->

## Common mistakes (and fixes)

- **Mistake:** publishing unedited AI output. **Fix:** run the E-E-A-T checklist; edit the experience section personally.
- **Mistake:** <!-- EDIT-ME: mistake from your own experience -->. **Fix:** <!-- EDIT-ME -->.

## FAQ

### What is {kw.lower()}?

<!-- EDIT-ME: 40-60 word answer, plain language. -->

### Is {kw.lower()} free to start?

<!-- EDIT-ME: honest answer with real cost boundaries. -->

### How long until results show?

<!-- EDIT-ME: realistic timeline with a citation. -->

## References

1. <!-- EDIT-ME: primary source title + URL -->
2. <!-- EDIT-ME: primary source title + URL -->
<<<KEYWORDS>>>
{kw} | {kw} tutorial, {kw} tools, {kw} best practices
"""


def make_provider(cfg: dict) -> LLMProvider:
    """cfg = config['content'] sub-dict.

    AUTOWEBPOST_PROVIDER (env) overrides the config file - handy for forcing the
    offline template provider in CI, or a one-off run with a different model.
    """
    kind = (os.environ.get("AUTOWEBPOST_PROVIDER") or cfg.get("provider") or "template").lower()
    if kind == "pollinations":
        return PollinationsProvider(model=cfg.get("pollinations_model", "openai"))
    if kind == "openai":
        from ..config import get_secret
        base = cfg.get("openai_base_url", "https://api.openai.com/v1")
        key = get_secret("OPENAI_API_KEY", "LLM_API_KEY")
        if not key:
            raise RuntimeError("provider=openai requires OPENAI_API_KEY (or LLM_API_KEY) in .env")
        return OpenAICompatProvider(base, key, cfg.get("openai_model", "gpt-4o-mini"))
    if kind == "gemini":
        from ..config import get_secret
        key = get_secret("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY")
        if not key:
            raise RuntimeError("provider=gemini requires GEMINI_API_KEY "
                               "(or OPENAI_API_KEY / LLM_API_KEY) in .env")
        return GeminiNativeProvider(key, cfg.get("gemini_model", "gemini-2.5-flash"))
    return TemplateProvider()


_MARKER = re.compile(r"<<<(TITLE|META|TAGS|BODY|KEYWORDS)>>>")


def _parse_sections(raw: str) -> dict:
    parts = {}
    matches = list(_MARKER.finditer(raw))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        parts[m.group(1)] = raw[m.end():end].strip()
    if "BODY" not in parts:  # model ignored format - treat whole output as body
        parts["BODY"] = raw.strip()
    return parts


def _render_faq(faq: List[FAQItem]) -> str:
    """Render structured FAQ items back into markdown.

    The FAQ is extracted into structured data for JSON-LD, but the questions
    and answers must ALSO stay visible in the body - an empty FAQ section on
    the published page both loses the featured-snippet opportunity and makes
    the FAQPage schema ineligible (it must mirror visible content).
    """
    if not faq:
        return "## FAQ\n"
    lines = ["## FAQ", ""]
    for item in faq:
        lines += [f"### {item.question}", "", item.answer, ""]
    return "\n".join(lines).rstrip() + "\n"


def _extract_faq(body: str) -> (str, List[FAQItem]):
    """Pull the FAQ H3 block out of the body into structured items, and put the
    rendered Q&A back in its place."""
    faq: List[FAQItem] = []
    m = re.search(r"^## FAQ\s*$(.*?)(?=^## \w|\Z)", body, re.M | re.S)
    if not m:
        return body, faq
    block = m.group(1)
    qas = re.findall(r"^###\s+(.+?)\s*\n+(.*?)(?=^###\s|\Z)", block, re.M | re.S)
    for q, a in qas:
        faq.append(FAQItem(question=q.strip(), answer=re.sub(r"\s+", " ", a).strip()))
    body = body.replace(m.group(0), _render_faq(faq))
    return body, faq


_REFERENCES_SECTION = re.compile(r"^## References\s*$(.*?)(?=^## \w|\Z)", re.M | re.S)


def _replace_references_section(body: str, refs: List[str]) -> str:
    """Make the body's References section list exactly ``refs``.

    Replaces it in place when present, otherwise appends one at the end.
    """
    section = references_section(refs).strip()
    if _REFERENCES_SECTION.search(body):
        return _REFERENCES_SECTION.sub(lambda m: section + "\n\n", body, count=1)
    return body.rstrip() + "\n\n" + section + "\n"


def _extract_references(body: str) -> (str, List[str]):
    """Collect the numbered reference list, ignoring unfilled EDIT-ME markers.

    Placeholders are instructions to the human author, not sources; keeping them
    out means a real ``--references`` list is no longer silently discarded.
    """
    m = re.search(r"^## References\s*$(.*?)(?=^## \w|\Z)", body, re.M | re.S)
    if not m:
        return body, []
    refs = [re.sub(r"^\d+\.\s*", "", l).strip() for l in m.group(1).splitlines() if l.strip()]
    refs = [r for r in refs if r and not _PLACEHOLDER.search(r)]
    return body, refs


class ContentEngine:
    def __init__(self, persona: Persona, provider: LLMProvider):
        self.persona = persona
        self.provider = provider
        self.fallback_used = False

    def _complete(self, system: str, user: str) -> str:
        try:
            return self.provider.complete(system, user)
        except Exception as e:
            if isinstance(self.provider, TemplateProvider):
                raise
            print(f"  ! provider '{self.provider.name}' failed ({type(e).__name__}: {str(e)[:120]})")
            print("  ! falling back to the offline template provider (structure done, you add specifics)")
            self.fallback_used = True
            self.provider = TemplateProvider()
            return self.provider.complete(system, user)

    def attach_images(self, draft: ArticleDraft, draft_dir=None) -> ArticleDraft:
        """Generate + inline images for a draft, writing them into draft_dir/images.

        Separated from generate() because the image folder has to be the same
        folder the article is saved to, and that folder name is derived from the
        slug, which only exists once the draft is generated.
        """
        try:
            from ..images.provider import images_for_draft
            draft.images = images_for_draft(draft, draft_dir=draft_dir)
            if draft.images:
                draft.body_markdown = _insert_images(draft)
        except Exception:  # images are best-effort; a text draft is still useful
            draft.images = []
        return draft

    def generate(self, brief: Brief, generate_images: bool = True, draft_dir=None) -> ArticleDraft:
        brief.author_name = brief.author_name or self.persona.name
        brief.author_tagline = brief.author_tagline or self.persona.tagline
        brief.author_experience_years = brief.author_experience_years or self.persona.experience_years
        brief.author_expertise = brief.author_expertise or self.persona.expertise
        brief.primary_keyword = brief.primary_keyword or brief.topic

        raw = self._complete(prompts.SYSTEM_PROMPT, prompts.build_user_prompt(brief))
        parts = _parse_sections(raw)

        title = parts.get("TITLE", f"{brief.primary_keyword.title()}: A Practical Guide").strip().strip('"')
        meta = parts.get("META", "").strip()
        if not meta or not 100 < len(meta) < 170:
            meta = build_meta_description(parts.get("BODY", "")[:400], brief.primary_keyword)
        tags = [clean_tag(t) for t in re.split(r"[,;]", parts.get("TAGS", "")) if t.strip()][:4]

        body = parts["BODY"]
        body, faq = _extract_faq(body)
        body, refs = _extract_references(body)
        refs = refs or [r for r in brief.references if r and r.strip()]
        # Real references must reach the page. If the body already has a
        # References section filled with EDIT-ME placeholders (the template
        # always does), swap the placeholders for the supplied sources instead
        # of leaving `--references` with no visible effect.
        if refs:
            body = _replace_references_section(body, refs)

        keywords_line = parts.get("KEYWORDS", "")
        if "|" in keywords_line:
            primary, *secondary = [k.strip() for k in keywords_line.split("|")]
            secondary = [s.strip() for s in ", ".join(secondary).split(",") if s.strip()][:6]
        else:
            primary, secondary = brief.primary_keyword, extract_keywords(body, 5)

        # Assemble final markdown with E-E-A-T blocks
        full = [
            body.strip(),
            "",
            "---",
            "",
            disclosure_block(self.persona),
            "",
            author_box(self.persona),
            "",
            trust_block(self.persona),
        ]
        draft = ArticleDraft(
            title=title,
            slug=slugify(title),
            meta_description=meta,
            primary_keyword=primary or brief.primary_keyword,
            secondary_keywords=secondary,
            tags=tags or [clean_tag(brief.primary_keyword), "guide"],
            body_markdown="\n".join(full),
            faq=faq,
            references=refs,
            generator=self.provider.name,
        )

        if generate_images:
            self.attach_images(draft, draft_dir)
        return draft


def _insert_images(draft: ArticleDraft) -> str:
    """Replace [IMAGE: alt] placeholders with markdown image includes."""
    body = draft.body_markdown
    for img in draft.images:
        pattern = re.compile(r"\[IMAGE:[^\]]*\]", re.I)
        if pattern.search(body):
            body = pattern.sub(f"![{img.alt_text}]({img.path})", body, count=1)
        else:
            body = body.replace("\n---\n", f"\n![{img.alt_text}]({img.path})\n\n---\n", 1)
    return body

"""AI image generation - free by default (Pollinations.ai, no API key).

Usage:
    from autowebpost.images.provider import generate_image, images_for_draft
"""
from __future__ import annotations

import re
from typing import List

import requests

from ..config import OUTPUT_DIR
from ..content import prompts
from ..models import ArticleDraft, ImageAsset

BASE = "https://image.pollinations.ai/prompt"


def build_prompt(topic: str, style_index: int = 0) -> str:
    return prompts.IMAGE_STYLE_PROMPT.format(
        topic=topic, style_hint=prompts.STYLE_HINTS[style_index % len(prompts.STYLE_HINTS)]
    )


def generate_image(prompt: str, out_path, width: int = 1200, height: int = 675,
                   model: str = "flux", seed: int | None = None) -> str:
    """Fetch an AI image from Pollinations (free, keyless) and save to out_path."""
    seed = seed if seed is not None else abs(hash(prompt)) % 10**8
    params = f"?width={width}&height={height}&model={model}&seed={seed}&nologo=true&enhance=true"
    url = f"{BASE}/{requests.utils.quote(prompt[:900])}{params}"
    r = requests.get(url, timeout=180, headers={"User-Agent": "AutoAIWebPost/0.1"})
    r.raise_for_status()
    if len(r.content) < 5000:
        raise RuntimeError(f"Image too small ({len(r.content)} bytes) - probably an error page")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    return str(out_path)


def images_for_draft(draft: ArticleDraft, max_images: int = 2) -> List[ImageAsset]:
    """Generate a hero image for the draft, based on its title/keyword."""
    assets: List[ImageAsset] = []
    folder = OUTPUT_DIR / "drafts" / draft.slug / "images"
    alts = re.findall(r"\[IMAGE:\s*([^\]]+)\]", draft.body_markdown, re.I)
    topics = [draft.primary_keyword or draft.title] * (1 if not alts else 0) + alts
    for i, alt in enumerate(topics[:max_images]):
        prompt = build_prompt(draft.primary_keyword or draft.title, i)
        path = folder / f"{draft.slug}-{'hero' if i == 0 else i}.jpg"
        try:
            generate_image(prompt, path)
            assets.append(ImageAsset(path=str(path), prompt=prompt, alt_text=alt or f"{draft.title} - illustrative image"))
        except Exception:
            continue
    return assets

"""E-E-A-T building blocks inserted into every article.

Google's quality framework: Experience, Expertise, Authoritativeness, Trust.
Nothing here is decorative - each block maps to a documented rater signal.
"""
from __future__ import annotations

from ..models import Persona

AI_DISCLOSURE = (
    "> **Editorial note:** This article was drafted with AI assistance and reviewed "
    "for accuracy by {name}. Facts are checked against the linked primary sources. "
    "Found an error? Contact us and we will correct it."
)


def author_box(persona: Persona) -> str:
    return persona.author_box_md()


def experience_block(persona: Persona, topic: str) -> str:
    """First-hand experience signal. The [EDIT] markers are intentional -
    replacing them with your real experience is the single highest-value
    E-E-A-T action, so the pipeline refuses to feel 'finished' without it."""
    return (
        f"## My experience with {topic.lower()}\n\n"
        f"I have worked with {topic.lower()} for over {persona.experience_years} years "
        "in my own projects. <!-- EDIT-ME: replace with 2-3 concrete sentences of "
        "first-hand experience - specific numbers, tools you personally ran, mistakes "
        "you made. First-hand experience is the 'E' that AI text cannot fake. -->\n"
    )


def references_section(refs: list) -> str:
    if not refs:
        return ""
    lines = ["## References and further reading", ""]
    lines += [f"{i}. {r}" for i, r in enumerate(refs, 1)]
    return "\n".join(lines) + "\n"


def trust_block(persona: Persona) -> str:
    contact = persona.website or "the contact page"
    return (
        "---\n\n"
        f"*Published by {persona.brand}. Editorial standards, corrections policy and "
        f"contact details: {contact}. We have no affiliate relationship with the tools "
        "mentioned unless explicitly stated.*\n"
    )


def disclosure_block(persona: Persona) -> str:
    return AI_DISCLOSURE.format(name=persona.name)


def eeat_qa_checklist() -> list:
    return [
        "Author box with real credentials present (Expertise)",
        "'My experience' section edited - [EDIT-ME] markers removed (Experience)",
        "At least 2 primary-source references linked (Trust)",
        "Numbers/dates fact-checked against references (Trust)",
        "Original images or screenshots used, with descriptive alt text",
        "Title contains primary keyword, reads naturally",
        "Meta description 120-158 chars, contains keyword, has a hook",
        "FAQ answers 3+ real long-tail questions (featured-snippet bait)",
        "Canonical URL set if cross-posted (duplicate-content safety)",
        "AI-assistance disclosure present where platform requires it",
    ]

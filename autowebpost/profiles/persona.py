"""Persona manager: ONE consistent identity across every platform.

E-E-A-T runs on entity consistency - the same name, bio, expertise and links
everywhere, so Google merges your presence into one author entity. This module
loads data/persona.yaml (copy from persona.example.yaml) and can bootstrap a
starter persona for you.

This describes *your* identity or your brand's pen name - it is the data you
type into signup forms yourself. It is not, and will not be, a fake-identity
generator for mass account creation (that violates every platform's ToS and
kills accounts fast).
"""
from __future__ import annotations

from ..config import DATA_DIR, load_yaml
from ..models import Persona

PERSONA_FILE = DATA_DIR / "persona.yaml"
EXAMPLE_FILE = DATA_DIR / "persona.example.yaml"


def load_persona(path=None) -> Persona:
    p = path or PERSONA_FILE
    if not p.exists():
        p = EXAMPLE_FILE
    return Persona.load(p)


def persona_path() -> str:
    return str(PERSONA_FILE)


def bootstrap(answers: dict) -> Persona:
    """Build data/persona.yaml from a few answers. If fields are missing we
    derive sensible E-E-A-T-grade text from what exists."""
    p = Persona(
        name=answers.get("name", ""),
        handle=answers.get("handle") or (answers.get("name", "author").lower().replace(" ", "")[:20]),
        brand=answers.get("brand") or f"{answers.get('name','Author')}'s Notes",
        email=answers.get("email", ""),
        website=answers.get("website", ""),
        tagline=answers.get("tagline", ""),
        expertise=[e.strip() for e in (answers.get("expertise") or "").split(",") if e.strip()],
        credentials=[c.strip() for c in (answers.get("credentials") or "").split(",") if c.strip()],
        experience_years=int(answers.get("years") or 5),
        social={k: v for k, v in (answers.get("social") or {}).items() if v},
    )
    exp = ", ".join(p.expertise[:3]) or "applied technology"
    p.bio_short = answers.get("bio_short") or f"{p.name} - {p.tagline or exp} specialist with {p.experience_years}+ years of hands-on work."
    p.bio_long = answers.get("bio_long") or (
        f"{p.name} has spent {p.experience_years}+ years working hands-on with {exp}. "
        f"{p.credentials[0] + ' ' if p.credentials else ''}"
        "Every article on this site is written from real projects, with tools that were "
        "actually run and results that were actually measured. Corrections and questions "
        f"are welcome via the contact page{(' at ' + p.website) if p.website else ''}."
    )
    p.save(PERSONA_FILE)
    return p

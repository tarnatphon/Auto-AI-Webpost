"""Curated catalog of free, high-authority publishing platforms."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .config import DATA_DIR, load_yaml


@dataclass
class Site:
    slug: str
    name: str
    url: str
    signup_url: str = ""
    da: int = 0                    # approximate Domain Authority (Moz-style), research 2026
    dofollow: bool = False
    api: str = "none"              # free | pro | none | manual-assist
    api_docs: str = ""
    publisher: str = ""            # autowebpost publisher slug, if implemented
    category: str = "blog"
    best_for: str = ""
    notes: str = ""
    env_keys: List[str] = field(default_factory=list)

    @property
    def auto_postable(self) -> bool:
        return bool(self.publisher) and self.api in ("free", "manual-assist")


def load_sites() -> List[Site]:
    raw = load_yaml(DATA_DIR / "sites.yaml") or []
    return [Site(**r) for r in raw]


def by_slug(slug: str) -> Site:
    for s in load_sites():
        if s.slug == slug:
            return s
    raise KeyError(f"Unknown site slug: {slug}")


def sites_table(sites: List[Site] | None = None, only_api: bool = False) -> str:
    sites = sites or load_sites()
    rows = [["SLUG", "PLATFORM", "~DA", "LINK", "API", "AUTOMATION", "USE FOR"]]
    for s in sorted(sites, key=lambda x: -x.da):
        if only_api and not s.auto_postable:
            continue
        rows.append([
            s.slug, s.name, str(s.da), "dofollow" if s.dofollow else "nofollow",
            s.api, ("auto: " + s.publisher) if s.publisher else "-",
            s.best_for[:38],
        ])
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    out = []
    for i, r in enumerate(rows):
        out.append("  ".join(c.ljust(widths[j]) for j, c in enumerate(r)))
        if i == 0:
            out.append("  ".join("-" * w for w in widths))
    return "\n".join(out)

"""Live-but-controlled smoke tests against real publisher APIs.

The test suite is (deliberately) fully offline: an autouse fixture hard-blocks
``requests`` so a stray test can never publish a public page. ``smoke`` exists
for the opposite, human-run case - verifying that credentials actually work and
that a real API accepts our payload, without turning a keyword research query
into forty live articles.

What it posts
-------------
By default it uses a tiny in-memory draft that is clearly marked as a smoke
test. It creates *drafts* on platforms that support them (dev.to, WordPress,
Blogger, Tumblr) and only touches public/undraftable endpoints (Telegraph,
Write.as, Mastodon, Reddit) when ``--force`` is passed.

Safety gates
------------
1. Everything is a dry run unless ``--live``.
2. Live runs require ``--confirm CONFIRM`` (must equal ``I am testing live``).
3. Live runs require gate ``SMOKE_ALLOW_LIVE=1`` (a second, quieter fail-safe so
   an accidental ``--live`` in the same shell can't fire by itself).
4. ``--force`` is required for platforms not capable of drafts.

Report
------
Each run writes ``output/smoke/smoke-<ts>.json`` and ``output/smoke/smoke-last.json``
so the result is inspectable afterwards.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .config import OUTPUT_DIR
from .models import ArticleDraft, FAQItem, Persona
from .platforms import get, get_many
from .profiles import load_persona

CONFIRM_TEXT = "I am testing live"
ALLOW_LIVE_ENV = "SMOKE_ALLOW_LIVE"
# Draft-capable platforms are safe to hit live without --force. Everything else
# creates public content immediately, so it must be explicitly forced.
DRAFT_SAFE = {"devto", "wordpress", "blogger", "tumblr"}
SMOKE_DIR = OUTPUT_DIR / "smoke"

# The createAccount/createPage calls on Telegraph write data/.telegraph_token and
# create pages, but it is still public content; it stays behind --force.
PUBLIC_PLATFORMS = {"telegraph", "writeas", "mastodon", "reddit"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_smoke_draft() -> ArticleDraft:
    """A tiny, obviously-a-test article. Never touches disk."""
    return ArticleDraft(
        title="Smoke test: Auto-AI-WebPost API connectivity",
        slug="smoke-test-auto-ai-webpost",
        meta_description="Automated connectivity smoke test. No real content; safe to delete.",
        primary_keyword="autowebpost smoke test",
        tags=["smoke-test"],
        body_markdown=(
            "This is an automated connectivity smoke test from Auto-AI-WebPost.\n\n"
            "It exists only to confirm that the platform API accepts our payload "
            "and that the configured credentials work. Please delete it.\n\n"
            "Happy publishing!\n"
        ),
        faq=[FAQItem(question="What is this?", answer="A connectivity smoke test.")],
        references=[],
        language="en",
        canonical_url="",
        created_at=_now_iso(),
        generator="smoke",
    )


@dataclass
class SmokeResult:
    platform: str
    ok: bool = False
    dry_run: bool = True
    skipped: bool = False
    url: str = ""
    detail: str = ""

    def summary(self) -> str:
        if self.skipped:
            return f"SKIP   {self.platform}: {self.detail}"
        flag = "DRY-RUN" if self.dry_run else ("OK " if self.ok else "FAIL")
        return f"[{flag}] {self.platform}: {self.detail or self.url or 'no detail'}"


@dataclass
class SmokeReport:
    created_at: str = field(default_factory=_now_iso)
    live: bool = False
    draft: str = ""
    platforms: List[str] = field(default_factory=list)
    results: List[SmokeResult] = field(default_factory=list)
    allowed: bool = True
    gate_message: str = ""

    @property
    def ok(self) -> bool:
        if not self.allowed:
            return False
        if not self.results:
            return False
        # Live smoke must have no failures; dry runs are informational and a
        # skipped/not-configured platform is not a failure of the command.
        return all((r.skipped or r.ok) for r in self.results)


def _save(report: SmokeReport) -> Path:
    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["results"] = [asdict(r) for r in report.results]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = SMOKE_DIR / f"smoke-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (SMOKE_DIR / "smoke-last.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def check_live_gate(live: bool, confirm: str, force: bool,
                    platforms: Optional[List[str]] = None, allow_live: bool = False) -> Optional[str]:
    """Return an error message when a live run is not allowed, else None."""
    if not live:
        return None
    if not (allow_live or os.environ.get(ALLOW_LIVE_ENV, "").strip() == "1"):
        return (f"live smoke requires {ALLOW_LIVE_ENV}=1 (or --allow-live on the CLI). "
                f"This is a second gate so --live doesn't fire on its own.")
    if confirm != CONFIRM_TEXT:
        return f"live smoke requires --confirm '{CONFIRM_TEXT}'."
    if not force:
        extra = [p for p in (platforms or []) if p in PUBLIC_PLATFORMS]
        if extra:
            return (f"these platforms create public content or need real credentials and are "
                    f"not draft-safe: {', '.join(sorted(extra))}. Pass --force to include them.")
    return None


def run_smoke(draft: Optional[ArticleDraft] = None,
              platforms: Optional[List[str]] = None,
              live: bool = False,
              confirm: str = "",
              force: bool = False,
              allow_live: bool = False,
              save_report: bool = True) -> SmokeReport:
    """Run connectivity checks and return (and optionally persist) a report.

    All live publishing is optional; without ``live`` the adapters only build
    their payloads (no HTTP, no credentials required).
    """
    platforms = platforms or ["devto", "wordpress", "blogger"]
    draft = draft or make_smoke_draft()
    persona = load_persona()

    report = SmokeReport(
        live=live,
        draft=getattr(draft, "slug", ""),
        platforms=list(platforms),
        allowed=True,
        gate_message="",
    )

    gate = check_live_gate(live, confirm, force, platforms=platforms, allow_live=allow_live)
    if gate:
        report.allowed = False
        report.gate_message = gate
        _save(report)
        return report

    for plat in platforms:
        try:
            pub = get(plat)
        except KeyError as ex:
            report.results.append(SmokeResult(plat, ok=False, dry_run=not live,
                                              detail=str(ex).strip("'\"")))
            continue
        # Live safety: draft-capable platforms are fine; public ones require force.
        if live and not force and plat not in DRAFT_SAFE:
            report.results.append(SmokeResult(plat, ok=False, dry_run=False, skipped=True,
                                              detail="not draft-safe; pass --force to create public content"))
            continue
        try:
            result = pub.publish(draft, persona, live=live, allow_public=force)
        except Exception as ex:
            report.results.append(SmokeResult(plat, ok=False, dry_run=not live,
                                              detail=f"{type(ex).__name__}: {ex}"))
            continue
        report.results.append(SmokeResult(plat, ok=result.ok, dry_run=result.dry_run,
                                          url=result.url, detail=result.detail))
    if save_report:
        _save(report)
    return report

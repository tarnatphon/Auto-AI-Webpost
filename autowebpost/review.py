"""The human-review gate: draft state, E-E-A-T checklist, EDIT-ME detection.

The whole safety model of this project rests on a human reading the draft before
it is published (see docs/03-compliance.md). This module is the model behind the
review dashboard (`autowebpost serve`) - it keeps all of the judgement logic in
one pure, testable place with no HTTP in it.

A draft's review state lives next to it in `review.yaml`:

    output/drafts/<date>-<slug>/
        article.md
        review.yaml      <- status + ticked checklist + notes

Some checklist items can be checked automatically from the draft itself
(FAQ count, canonical URL, meta length...). Those are reported as `auto` so the
dashboard can show "verified" vs "you must tick this yourself" - the point is to
make the gate honest, not to let anyone rubber-stamp it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .config import OUTPUT_DIR, load_yaml, save_yaml
from .content.eeat import eeat_qa_checklist
from .models import ArticleDraft, Persona

REVIEW_FILENAME = "review.yaml"

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)

# Unfilled template markers. Their presence anywhere in the article means the
# human has not finished the draft.
EDIT_ME = re.compile(r"<!--\s*EDIT-ME\b.*?-->", re.I | re.S)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ReviewState:
    status: str = STATUS_PENDING
    checklist: Dict[str, bool] = field(default_factory=dict)
    notes: str = ""
    decided_at: str = ""

    def to_dict(self) -> dict:
        return {"status": self.status, "checklist": dict(self.checklist),
                "notes": self.notes, "decided_at": self.decided_at}

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewState":
        data = data or {}
        status = data.get("status", STATUS_PENDING)
        return cls(
            status=status if status in STATUSES else STATUS_PENDING,
            checklist={k: bool(v) for k, v in (data.get("checklist") or {}).items()},
            notes=data.get("notes", "") or "",
            decided_at=data.get("decided_at", "") or "",
        )


def review_path(draft_folder: Path) -> Path:
    return Path(draft_folder) / REVIEW_FILENAME


def load_review(draft_folder: Path) -> ReviewState:
    """Load review state, tolerating a missing or unparseable file."""
    p = review_path(draft_folder)
    if not p.exists():
        return ReviewState()
    try:
        data = load_yaml(p)
    except Exception:
        return ReviewState()
    # a hand-edited file may parse as a string/list rather than a mapping
    return ReviewState.from_dict(data if isinstance(data, dict) else {})


def save_review(draft_folder: Path, state: ReviewState) -> ReviewState:
    save_yaml(review_path(draft_folder), state.to_dict())
    return state


def set_decision(draft_folder: Path, status: str) -> ReviewState:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    state = load_review(draft_folder)
    state.status = status
    state.decided_at = _now_iso() if status != STATUS_PENDING else ""
    return save_review(draft_folder, state)


def toggle_checklist(draft_folder: Path, item: str, done: bool) -> Dict[str, bool]:
    state = load_review(draft_folder)
    state.checklist[item] = bool(done)
    save_review(draft_folder, state)
    return state.checklist


def set_notes(draft_folder: Path, notes: str) -> ReviewState:
    state = load_review(draft_folder)
    state.notes = notes or ""
    return save_review(draft_folder, state)


# --------------------------------------------------------------------------
# EDIT-ME detection
# --------------------------------------------------------------------------

def find_edit_me(text: str) -> List[str]:
    """Every unfilled EDIT-ME instruction still in the text."""
    return [re.sub(r"\s+", " ", m.group(0)).strip() for m in EDIT_ME.finditer(text or "")]


def unresolved_markers(draft: ArticleDraft) -> List[str]:
    """EDIT-ME markers anywhere in the draft - body, FAQ answers, references."""
    text = draft.body_markdown or ""
    text += "\n".join(f"{f.question} {f.answer}" for f in draft.faq)
    text += "\n".join(draft.references)
    return find_edit_me(text)


# --------------------------------------------------------------------------
# Auto-verified checklist items
# --------------------------------------------------------------------------

def _kw(draft: ArticleDraft) -> str:
    return (draft.primary_keyword or "").lower().strip()


def _auto_checks(draft: ArticleDraft, persona: Optional[Persona]) -> Dict[str, Optional[bool]]:
    """Checklist items we can verify from the draft itself.

    Value is True/False when verifiable, None when only a human can judge it.
    """
    meta = draft.meta_description or ""
    kw = _kw(draft)
    body = draft.body_markdown or ""
    checklist = eeat_qa_checklist()

    def by(index: int) -> str:
        return checklist[index]

    return {
        by(0): (persona.name in body) if persona else None,          # author box
        by(1): not find_edit_me(body),                               # experience edited
        by(2): len(draft.references) >= 2,                           # 2+ sources
        by(3): None,                                                 # fact-checking: human only
        by(4): bool(draft.images) and all(i.alt_text for i in draft.images),
        # only the objective half is checkable - "reads naturally" is still yours
        by(5): bool(kw) and kw in (draft.title or "").lower(),
        by(6): bool(kw) and 120 <= len(meta) <= 158 and kw in meta.lower(),
        by(7): len(draft.faq) >= 3,                                  # 3+ FAQ questions
        by(8): bool(draft.canonical_url),                            # canonical set
        by(9): "Editorial note" in body,                             # AI disclosure
    }


def checklist_report(draft: ArticleDraft, persona: Optional[Persona],
                     review: Optional[ReviewState] = None) -> List[dict]:
    """Per-item status: auto-verified, manually ticked, or outstanding."""
    review = review or ReviewState()
    auto = _auto_checks(draft, persona)
    out = []
    for item in eeat_qa_checklist():
        verified = auto.get(item)
        ticked = bool(review.checklist.get(item))
        out.append({
            "item": item,
            "auto": verified,               # True / False / None (human-only)
            "manual": ticked,
            "done": bool(verified) or ticked,
            "human_only": verified is None,
        })
    return out


def checklist_progress(report: List[dict]) -> dict:
    total = len(report)
    done = sum(1 for r in report if r["done"])
    return {"total": total, "done": done, "complete": total > 0 and done == total}


def is_publishable(draft: ArticleDraft, persona: Optional[Persona],
                   review: Optional[ReviewState] = None) -> bool:
    """A draft may only be published once a human approved it.

    The checklist is advisory (it feeds the UI); the decision is the gate.
    """
    review = review or ReviewState()
    return review.status == STATUS_APPROVED


# --------------------------------------------------------------------------
# Draft discovery / summaries
# --------------------------------------------------------------------------

def iter_draft_folders(base_dir: Optional[Path] = None) -> List[Path]:
    """Draft folders, newest first. A folder without article.md is not a draft."""
    root = Path(base_dir) if base_dir else (OUTPUT_DIR / "drafts")
    if not root.exists():
        return []
    return sorted((p for p in root.iterdir()
                   if p.is_dir() and (p / "article.md").exists()), reverse=True)


def load_draft_folder(folder: Path) -> Optional[ArticleDraft]:
    """Load a draft, or None if the folder holds no article.md."""
    article = Path(folder) / "article.md"
    if not article.exists():
        return None
    try:
        return ArticleDraft.load(article)
    except Exception:
        return None


def draft_summary(folder: Path, draft: ArticleDraft,
                  persona: Optional[Persona] = None) -> dict:
    """Everything the dashboard list needs for one draft."""
    folder = Path(folder)
    review = load_review(folder)
    report = checklist_report(draft, persona, review)
    progress = checklist_progress(report)
    markers = unresolved_markers(draft)
    words = len((draft.body_markdown or "").split())
    return {
        "id": folder.name,
        "folder": str(folder),
        "title": draft.title or folder.name,
        "slug": draft.slug,
        "status": review.status,
        "decided_at": review.decided_at,
        "notes": review.notes,
        "primary_keyword": draft.primary_keyword,
        "meta_description": draft.meta_description,
        "tags": draft.tags,
        "canonical_url": draft.canonical_url,
        "generator": draft.generator,
        "words": words,
        "faq_count": len(draft.faq),
        "reference_count": len(draft.references),
        "image_count": len(draft.images),
        "markers": markers,
        "marker_count": len(markers),
        "checklist": report,
        "progress": progress,
        "publishable": is_publishable(draft, persona, review),
    }

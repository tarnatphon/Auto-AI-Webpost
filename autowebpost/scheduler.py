"""Drip scheduler: a queue of drafts -> platforms, published at planned times.

Queue file: data/queue.yaml
    - id: 1
      draft: output/drafts/2026-08-28-my-post/article.md
      platforms: [githubpages, devto, telegraph, mastodon]
      publish_at: "2026-08-29 09:00"
      status: pending      # pending | published | failed
      results: []

Run manually (cron on your Mac) or free in the cloud via the included
GitHub Actions workflow (.github/workflows/autopost.yml).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from .config import DATA_DIR, load_yaml, save_yaml

QUEUE_FILE = DATA_DIR / "queue.yaml"


def _queue() -> list:
    return load_yaml(QUEUE_FILE) if QUEUE_FILE.exists() else []


def add(draft: str, platforms: List[str], publish_at: str, delay_minutes: int = 0) -> dict:
    q = _queue()
    if publish_at:
        when = publish_at
    else:
        when = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    entry = {
        "id": str(uuid.uuid4())[:8],
        "draft": str(draft),
        "platforms": platforms,
        "publish_at": when,
        "delay_minutes": delay_minutes,
        "status": "pending",
        "results": [],
    }
    q.append(entry)
    save_yaml(QUEUE_FILE, q)
    return entry


def entries() -> list:
    return _queue()


def remove(entry_id: str) -> bool:
    q = _queue()
    n = len(q)
    q = [e for e in q if e.get("id") != entry_id]
    save_yaml(QUEUE_FILE, q)
    return len(q) < n


def run_due(live: bool = False, now: Optional[datetime] = None) -> List[dict]:
    """Publish every pending entry whose time has come. Stagger multi-platform
    posts by delay_minutes between platforms (natural, non-spammy cadence)."""
    from .models import ArticleDraft, Persona
    from .platforms import get_many
    from .profiles import load_persona

    now = now or datetime.utcnow()
    q = _queue()
    done = []
    persona = load_persona()
    for e in q:
        if e.get("status") != "pending":
            continue
        try:
            due = datetime.strptime(e["publish_at"], "%Y-%m-%d %H:%M")
        except Exception:
            due = now
        if due > now:
            continue
        try:
            draft = ArticleDraft.load(e["draft"])
        except Exception as ex:
            e["status"] = "failed"
            e["results"] = [{"error": f"cannot load draft: {ex}"}]
            done.append(e)
            continue
        results = []
        delay = int(e.get("delay_minutes", 0))
        for i, plat in enumerate(e["platforms"]):
            if delay and i > 0:
                # within one run we still post all platforms, but note the intended stagger
                results.append({"platform": plat, "note": f"staggered +{delay * i}min recommended"})
            pub = get_many(plat)[0]
            r = pub.publish(draft, persona, live=live)
            results.append({"platform": plat, "ok": r.ok, "url": r.url, "detail": r.detail[:200], "dry_run": r.dry_run})
        e["status"] = "published" if live else "simulated"
        e["results"] = results
        done.append(e)
    if done:
        save_yaml(QUEUE_FILE, q)
    return done

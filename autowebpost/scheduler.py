"""Drip scheduler: a queue of drafts -> platforms, published at planned times.

Queue file: data/queue.yaml
    - id: 1
      draft: output/drafts/2026-08-28-my-post/article.md
      platforms: [githubpages, devto, telegraph, mastodon]
      publish_at: "2026-08-29 09:00"
      status: pending        # pending | retrying | published | simulated | failed
      attempts: 0
      max_attempts: 3
      retry_minutes: 15
      next_attempt_at: "2026-08-29 09:15"
      platform_status: {devto: ok, mastodon: failed}
      results: []

Run manually (cron on your Mac) or free in the cloud via the included
GitHub Actions workflow (.github/workflows/autopost.yml).

Failover model:
- Every entry gets up to ``max_attempts`` runs.
- A platform that already succeeded is skipped on later attempts, so a partial
  failure only retries what actually failed.
- Missing credentials / network / API errors are retryable (you may have fixed
  the key or the network by the next run).
- An unknown platform slug is a config error and is *not* retried; it marks the
  entry failed immediately.
- ``retrying`` entries are picked up on the next ``run_due`` once
  ``next_attempt_at`` has passed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from .config import DATA_DIR, load_yaml, save_yaml, utc_now, utc_stamp

QUEUE_FILE = DATA_DIR / "queue.yaml"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_MINUTES = 15


def _queue() -> list:
    # An empty/whitespace queue file parses as None - treat that as empty.
    return (load_yaml(QUEUE_FILE) if QUEUE_FILE.exists() else None) or []


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _parse_stamp(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except Exception:
        return None


def add(draft: str, platforms: List[str], publish_at: str, delay_minutes: int = 0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS, retry_minutes: int = DEFAULT_RETRY_MINUTES) -> dict:
    q = _queue()
    when = publish_at or utc_stamp()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "draft": str(draft),
        "platforms": list(platforms),
        "publish_at": when,
        "delay_minutes": int(delay_minutes or 0),
        "max_attempts": int(max_attempts or DEFAULT_MAX_ATTEMPTS),
        "retry_minutes": int(retry_minutes or DEFAULT_RETRY_MINUTES),
        "attempts": 0,
        "status": "pending",
        "next_attempt_at": when,
        "platform_status": {},
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


def _entry_due(e: dict, now: datetime) -> Optional[datetime]:
    """Return the next scheduled time for an entry, or None if it is not pending.

    ``retrying`` entries run when their ``next_attempt_at`` is due; other open
    entries run at their ``publish_at``.
    """
    status = e.get("status")
    if status in ("published", "simulated", "failed"):
        return None
    if status == "retrying":
        # If no attempt time exists (older queue), fall back to publish_at.
        return _parse_stamp(str(e.get("next_attempt_at") or "")) or _parse_stamp(str(e.get("publish_at") or ""))
    return _parse_stamp(str(e.get("publish_at") or "")) or now


def _platform_state(e: dict) -> dict:
    """Platform state carried in the entry, back-filled from old results."""
    state = dict(e.get("platform_status") or {})
    for r in e.get("results") or []:
        plat = r.get("platform")
        if plat and r.get("ok") is True and state.get(plat) != "ok":
            state[plat] = "ok"
    return state


def _publish_platform(pub, draft, persona, live: bool, plat: str):
    """Run one publish and normalise the result dict + state."""
    try:
        r = pub.publish(draft, persona, live=live)
    except Exception as ex:  # adapter itself threw (shouldn't, but be safe)
        return {"platform": plat, "ok": False, "url": "", "detail": f"{type(ex).__name__}: {ex}", "dry_run": not live}, "failed"
    result = {"platform": plat, "ok": r.ok, "url": r.url,
              "detail": r.detail[:200], "dry_run": r.dry_run}
    return result, ("ok" if r.ok else "failed")


def run_due(live: bool = False, now: Optional[datetime] = None,
            retry_minutes: Optional[int] = None) -> List[dict]:
    """Publish every entry whose time has come, retrying failures later.

    One bad platform no longer aborts the run: only its entry fails (or is
    marked for retry), the rest of the queue still proceeds. Already-successful
    platforms are skipped on retry so nothing is double-posted.
    """
    from .models import ArticleDraft, Persona
    from .platforms import get
    from .profiles import load_persona

    now = now or utc_now()
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    q = _queue()
    done: List[dict] = []
    persona = load_persona()

    for e in q:
        due = _entry_due(e, now)
        if due is None:
            continue
        if due > now:
            continue

        # Normalise per-entry settings (legacy/first-run entries get defaults).
        max_attempts = int(e.get("max_attempts") or DEFAULT_MAX_ATTEMPTS)
        retry_minutes = int(retry_minutes if retry_minutes is not None
                            else e.get("retry_minutes") or DEFAULT_RETRY_MINUTES)
        attempts = int(e.get("attempts") or 0)
        platform_status = _platform_state(e)

        if attempts >= max_attempts:
            e["status"] = "failed"
            e.setdefault("results", []).append({
                "platform": "", "ok": False, "url": "",
                "detail": f"exhausted {max_attempts} attempt(s); run the platform manually or fix the cause", "dry_run": not live,
            })
            e["attempts"] = attempts
            done.append(e)
            continue

        # Load draft (a missing/syncing file is exactly the kind of transient
        # failure worth retrying on the next schedule).
        try:
            draft = ArticleDraft.load(e["draft"])
        except Exception as ex:
            attempts += 1
            e["attempts"] = attempts
            e["platform_status"] = platform_status
            if attempts < max_attempts:
                e["status"] = "retrying"
                e["next_attempt_at"] = _stamp(now + timedelta(minutes=retry_minutes))
                e.setdefault("results", []).append({"platform": "", "ok": False, "url": "",
                                                    "detail": f"cannot load draft: {ex} (retry {attempts}/{max_attempts})", "dry_run": not live})
            else:
                e["status"] = "failed"
                e.setdefault("results", []).append({"platform": "", "ok": False, "url": "",
                                                    "detail": f"cannot load draft: {ex} (exhausted {max_attempts} attempts)", "dry_run": not live})
            done.append(e)
            continue

        to_attempt = [p for p in e.get("platforms") or [] if platform_status.get(p) != "ok"]
        if not to_attempt:
            # Everything already succeeded in an earlier run.
            e["status"] = "published" if live else "simulated"
            e["attempts"] = attempts + 1
            e["platform_status"] = platform_status
            done.append(e)
            continue

        delay = int(e.get("delay_minutes") or 0)
        permanent_failure = False
        for i, plat in enumerate(to_attempt):
            if delay and i > 0:
                e.setdefault("results", []).append({"platform": plat, "note": f"staggered +{delay * i}min recommended"})
            try:
                pub = get(plat)
            except KeyError as ex:
                # Unknown slug is a config error; retrying will never fix it.
                platform_status[plat] = "bad_config"
                permanent_failure = True
                e.setdefault("results", []).append({"platform": plat, "ok": False, "url": "",
                                                    "detail": str(ex).strip("'\""), "dry_run": not live})
                continue
            result, state = _publish_platform(pub, draft, persona, live, plat)
            platform_status[plat] = state
            e.setdefault("results", []).append(result)

        e["attempts"] = attempts + 1
        e["platform_status"] = platform_status
        e["retry_minutes"] = retry_minutes
        e["max_attempts"] = max_attempts

        remaining_failed = any(v in ("failed", "bad_config") for v in platform_status.values())
        if permanent_failure:
            e["status"] = "failed"
        elif not remaining_failed:
            e["status"] = "published" if live else "simulated"
            e["next_attempt_at"] = e["publish_at"]
        elif e["attempts"] >= max_attempts:
            e["status"] = "failed"
        else:
            e["status"] = "retrying"
            e["next_attempt_at"] = _stamp(now + timedelta(minutes=retry_minutes))
        done.append(e)

    if done:
        save_yaml(QUEUE_FILE, q)
    return done

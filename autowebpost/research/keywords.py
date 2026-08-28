"""Free keyword research - zero API cost.

Sources: Google Autocomplete (client=firefox JSON endpoint) with a
DuckDuckGo autocomplete fallback. Returns real user query strings -
exactly the long-tail phrasing to use in titles, H2s and FAQ answers.
"""
from __future__ import annotations

import requests
from typing import List

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def suggest(keyword: str) -> List[str]:
    """Google autocomplete suggestions for a seed keyword."""
    try:
        r = requests.get(
            "https://suggestqueries.google.com/complete/search",
            params={"client": "firefox", "q": keyword}, headers=UA, timeout=15)
        r.raise_for_status()
        return list(r.json()[1])[:12]
    except Exception:
        try:
            r = requests.get("https://duckduckgo.com/ac/", params={"q": keyword, "type": "list"}, headers=UA, timeout=15)
            r.raise_for_status()
            return [x[0] for x in r.json()][:12]
        except Exception:
            return []


def expand(keyword: str) -> dict:
    """Alphabet + question expansions of a seed keyword -> long-tail map."""
    mods_a = [keyword] + [f"{keyword} {c}" for c in "abcdefg"]
    mods_q = [f"{w} {keyword}" for w in ["how to", "best", "why", "what is", "free", "2026", "vs"]]
    out = {"seed": keyword, "alphabet": [], "questions": []}
    for m in mods_a:
        out["alphabet"] += [s for s in suggest(m) if s.lower() != keyword.lower()]
    for m in mods_q:
        out["questions"] += [s for s in suggest(m) if s.lower() != keyword.lower()]
    out["alphabet"] = sorted(set(out["alphabet"]))[:20]
    out["questions"] = sorted(set(out["questions"]))[:20]
    return out

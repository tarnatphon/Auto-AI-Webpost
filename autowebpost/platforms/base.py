"""Publisher base class. All adapters publish through OFFICIAL APIs of the
platform, using YOUR account credentials stored in .env - never scraped forms.

Safety model: every publish call is a DRY RUN unless live=True.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Dict, List

import requests

from ..config import get_secret, missing_secrets
from ..models import ArticleDraft, Persona, PostResult

UA = {"User-Agent": "AutoAIWebPost/0.1 (+https://github.com/)"}


class Publisher(ABC):
    slug: str = "base"
    name: str = "Base"
    env_keys: List[str] = []
    docs: str = ""

    def missing_env(self) -> List[str]:
        return missing_secrets(self.env_keys)

    @abstractmethod
    def build_payload(self, draft: ArticleDraft, persona: Persona) -> Dict:
        """Return the exact request payload that would be sent."""

    def publish(self, draft: ArticleDraft, persona: Persona, live: bool = False, **kw) -> PostResult:
        payload = self.build_payload(draft, persona)
        preview = json.dumps(payload, ensure_ascii=False, indent=2)
        preview = preview if len(preview) < 1600 else preview[:1600] + "\n... (truncated)"
        if not live:
            return PostResult(self.slug, True, detail=f"DRY RUN payload:\n{preview}", dry_run=True)
        missing = self.missing_env()
        if missing:
            return PostResult(self.slug, False, detail=f"missing env: {', '.join(missing)} (see .env.example)")
        try:
            return self._publish_live(draft, persona, payload, **kw)
        except requests.HTTPError as e:
            body = ""
            try:
                body = e.response.text[:400]
            except Exception:
                pass
            return PostResult(self.slug, False, detail=f"HTTP {e.response.status_code if e.response is not None else '?'} {body}")
        except Exception as e:
            return PostResult(self.slug, False, detail=f"{type(e).__name__}: {e}")

    def _publish_live(self, draft: ArticleDraft, persona: Persona, payload: Dict, **kw) -> PostResult:
        raise NotImplementedError(f"{self.slug}: live publishing not implemented")

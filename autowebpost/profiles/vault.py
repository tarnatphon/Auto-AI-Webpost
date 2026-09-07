"""Secrets + registration-status vault.

- Secrets: .env only (gitignored). Never stored in the repo, never committed.
- Per-site generated passwords: data/.credentials.local.yaml (gitignored).
- Registration progress: data/registration_status.yaml (gitignored).
"""
from __future__ import annotations

import secrets
import string
from pathlib import Path
from typing import Dict, Optional

from ..config import DATA_DIR, load_env, load_yaml, save_yaml

CRED_FILE = DATA_DIR / ".credentials.local.yaml"
STATUS_FILE = DATA_DIR / "registration_status.yaml"

_CHARS = string.ascii_letters + string.digits
_AMBIGUOUS = set("0O1lI|`'")


class Vault:
    def __init__(self):
        load_env()

    # ---------- passwords ----------
    @staticmethod
    def generate_password(length: int = 20) -> str:
        """Password-generator for the accounts YOU create. One unique password
        per site, no dictionary words. Store it in your real password manager."""
        while True:
            pw = "".join(secrets.choice(_CHARS) for _ in range(length))
            if not any(c in _AMBIGUOUS for c in pw) and any(c.isdigit() for c in pw) and any(c.islower() for c in pw) and any(c.isupper() for c in pw):
                return pw

    def store_credential(self, site: str, password: str, username: str = "", note: str = "") -> None:
        data = {}
        if CRED_FILE.exists():
            data = load_yaml(CRED_FILE) or {}
        data[site] = {"username": username, "password": password, "note": note or "generated; ROTATE after first login"}
        save_yaml(CRED_FILE, data)

    def get_credential(self, site: str) -> Optional[Dict]:
        if not CRED_FILE.exists():
            return None
        return (load_yaml(CRED_FILE) or {}).get(site)

    # ---------- registration status ----------
    def set_status(self, site: str, status: str, detail: str = "") -> None:
        data = {}
        if STATUS_FILE.exists():
            data = load_yaml(STATUS_FILE) or {}
        data[site] = {"status": status, "detail": detail}
        save_yaml(STATUS_FILE, data)

    def all_status(self) -> Dict:
        if not STATUS_FILE.exists():
            return {}
        return load_yaml(STATUS_FILE) or {}

    def status_table(self) -> str:
        st = self.all_status()
        if not st:
            return ("No registrations tracked yet.\n"
                    "Next: python -m autowebpost.cli register githubpages devto telegraph\n"
                    "      (add --open to open each signup page in your browser)")
        rows = [("SITE", "STATUS", "DETAIL")]
        rows += [(k, v.get("status", "?"), (v.get("detail", "") or "")[:50]) for k, v in sorted(st.items())]
        w = [max(len(r[i]) for r in rows) for i in range(3)]
        return "\n".join("  ".join(c.ljust(w[j]) for j, c in enumerate(r)) for r in rows)

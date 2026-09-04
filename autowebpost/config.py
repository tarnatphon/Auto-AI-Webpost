"""Configuration + secrets handling.

Secrets live in `.env` (gitignored) or real environment variables.
Non-secret settings live in `data/config.yaml` (falls back to `config.example.yaml`).
"""
from __future__ import annotations

import os
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def utc_now() -> datetime:
    """Timezone-aware UTC 'now'.

    Replaces the deprecated (and naive) ``datetime.utcnow()``; keeping this in
    one place means the queue, the draft folders and the GitHub Pages filename
    all agree on what "today" means.
    """
    return datetime.now(timezone.utc)


def utc_today_iso() -> str:
    return utc_now().date().isoformat()


def utc_stamp() -> str:
    """'YYYY-MM-DD HH:MM' in UTC - the format the queue file stores."""
    return utc_now().strftime("%Y-%m-%d %H:%M")


def load_env(path: Optional[pathlib.Path] = None) -> None:
    """Tiny .env loader (no external deps). Never overrides real env vars."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def get_secret(*names: str, default: str = "") -> str:
    """Return the first matching environment variable."""
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return default


def load_yaml(path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def save_yaml(path, data: Any) -> None:
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)


def load_config(path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    p = path or DATA_DIR / "config.yaml"
    if not p.exists():
        p = DATA_DIR / "config.example.yaml"
    if not p.exists():
        return {}
    return load_yaml(p) or {}


def missing_secrets(required: List[str]) -> List[str]:
    return [k for k in required if not get_secret(k)]

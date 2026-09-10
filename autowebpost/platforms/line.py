"""LINE Official Account publisher - Messaging API broadcast.

Broadcast messages to all friends/followers of your LINE Official Account.
Official API endpoint: POST https://api.line.me/v2/bot/message/broadcast

Setup:
1. Go to https://developers.line.biz/ -> Create Provider & Messaging API channel.
2. Messaging API tab -> Channel access token (long-lived) -> Issue.
3. Set LINE_CHANNEL_ACCESS_TOKEN in .env.
"""
from __future__ import annotations

from typing import Dict, List, Optional
import requests

from ..config import get_secret
from ..models import ArticleDraft, Persona, PostResult
from .base import UA, Publisher

API_BOT_INFO = "https://api.line.me/v2/bot/info"
API_MESSAGE_QUOTA = "https://api.line.me/v2/bot/message/quota"
API_MESSAGE_CONSUMPTION = "https://api.line.me/v2/bot/message/quota/consumption"
API_BROADCAST = "https://api.line.me/v2/bot/message/broadcast"


def get_bot_info(token: str) -> dict:
    """Fetch LINE bot info (displayName, basicId, etc.)."""
    r = requests.get(API_BOT_INFO, headers={"Authorization": f"Bearer {token}", **UA}, timeout=15)
    r.raise_for_status()
    return r.json()


def get_quota(token: str) -> dict:
    """Fetch LINE monthly message quota."""
    r = requests.get(API_MESSAGE_QUOTA, headers={"Authorization": f"Bearer {token}", **UA}, timeout=15)
    r.raise_for_status()
    return r.json()


def get_quota_consumption(token: str) -> dict:
    """Fetch LINE monthly message quota consumption (totalUsage)."""
    try:
        r = requests.get(API_MESSAGE_CONSUMPTION, headers={"Authorization": f"Bearer {token}", **UA}, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def send_broadcast(token: str, messages: List[dict]) -> dict:
    """Send broadcast message via LINE Messaging API."""
    r = requests.post(
        API_BROADCAST,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            **UA,
        },
        json={"messages": messages},
        timeout=60,
    )
    if not r.ok:
        err_msg = ""
        try:
            err_data = r.json()
            err_msg = err_data.get("message") or str(err_data)
        except Exception:
            err_msg = r.text[:300]
        raise requests.HTTPError(f"{r.status_code} {r.reason}: {err_msg}", response=r)

    try:
        return r.json()
    except Exception:
        return {}


class LinePublisher(Publisher):
    slug = "line"
    name = "LINE Official Account"
    env_keys = ["LINE_CHANNEL_ACCESS_TOKEN"]
    docs = "https://developers.line.biz/en/reference/messaging-api/#send-broadcast-message"

    def build_payload(self, draft: ArticleDraft, persona: Persona) -> dict:
        messages = []
        text_parts = [f"📢 {draft.title}"]
        if draft.meta_description:
            text_parts.append(draft.meta_description)
        link = draft.canonical_url or (draft.images[0].url if draft.images and draft.images[0].url else "")
        if link:
            text_parts.append(f"🔗 {link}")

        text_content = "\n\n".join(text_parts).strip()
        messages.append({
            "type": "text",
            "text": text_content[:5000],
        })

        if draft.images and draft.images[0].url and draft.images[0].url.startswith("https://"):
            img_url = draft.images[0].url
            messages.append({
                "type": "image",
                "originalContentUrl": img_url,
                "previewImageUrl": img_url,
            })

        return {"messages": messages}

    def _publish_live(self, draft: ArticleDraft, persona: Persona, payload: dict, **kw) -> PostResult:
        token = get_secret("LINE_CHANNEL_ACCESS_TOKEN")
        bot_name = ""
        try:
            bot_data = get_bot_info(token)
            bot_name = bot_data.get("displayName", "")
        except Exception:
            pass

        try:
            quota_data = get_quota(token)
            consumption = get_quota_consumption(token)
            used = consumption.get("totalUsage", 0)
            if quota_data.get("type") == "limited":
                total = quota_data.get("value", 0)
                if total <= used:
                    return PostResult(self.slug, False, detail=f"monthly message quota exhausted ({used}/{total} used)")
        except Exception:
            pass

        messages = payload.get("messages", [])
        if not messages:
            return PostResult(self.slug, False, detail="payload contains no messages")

        send_broadcast(token, messages)
        detail = "broadcast sent to OA followers"
        if bot_name:
            detail += f" (bot: {bot_name})"
        return PostResult(self.slug, True, detail=detail)

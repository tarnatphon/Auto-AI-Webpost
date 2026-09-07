"""Registration assistant - prepares YOUR account signups, keeps you ToS-safe.

What it DOES:
  * builds a per-site signup plan (URL + exactly which persona fields go where)
  * generates one strong unique password per site, stored in the local vault
  * opens the signup page in your browser (--open) so YOU complete the form
  * tracks status: planned -> registered -> verified -> api-key-set

What it deliberately does NOT do:
  * auto-submit signup forms, solve CAPTCHAs, or mass-create accounts.
    Automated account creation violates the ToS of essentially every platform,
    gets domains flagged as spam, and undoes the SEO you are building.
    One account per site, created by you, posting via the official API - that
    is what survives and ranks.
"""
from __future__ import annotations

import webbrowser
from dataclasses import dataclass, field
from typing import List

from ..catalog import Site, by_slug, load_sites
from .vault import Vault

DEFAULT_SITES = ["devto", "telegraph", "wordpress", "blogger", "tumblr", "mastodon", "writeas", "githubpages"]


@dataclass
class SignupPlan:
    site: Site
    steps: List[str] = field(default_factory=list)
    fields: dict = field(default_factory=dict)
    password: str = ""


class RegistrationAssistant:
    def __init__(self, persona, vault: Vault | None = None):
        self.persona = persona
        self.vault = vault or Vault()

    def plan(self, slugs: List[str], fresh_password: bool = True) -> List[SignupPlan]:
        plans = []
        for slug in slugs:
            site = by_slug(slug)
            p = SignupPlan(site=site)
            u = self.persona
            p.fields = {
                "display name / username": u.name if "blogger" not in slug else (u.handle or u.name),
                "email": u.email or "<your email - use one you control>",
                "handle": u.handle,
                "bio / about": u.bio_short,
                "website": u.website,
                "profile links": ", ".join(v for v in u.social.values() if v),
                "expertise tags": ", ".join(u.expertise[:5]),
            }
            existing = self.vault.get_credential(slug)
            p.password = self.vault.generate_password() if (fresh_password or not existing) else existing["password"]
            p.steps = self._steps_for(site)
            plans.append(p)
        return plans

    def _steps_for(self, site: Site) -> List[str]:
        common = [
            f"Open {site.signup_url or site.url}",
            "Complete the signup form with the fields below (you type them in - never automated)",
            "Verify your email, then complete your PROFILE immediately: avatar, bio, website, expertise - a complete profile is an E-E-A-T trust signal",
        ]
        specific = {
            "devto": ["Settings -> Extensions -> generate DEVTO_API_KEY -> put it in .env"],
            "wordpress": ["Users -> Profile -> Application Passwords -> create one -> WP_SITE/WP_USER/WP_APP_PASSWORD in .env"],
            "blogger": ["Get OAuth token via https://developers.google.com/oauthplayground (scope: blogger) -> BLOGGER_ACCESS_TOKEN, BLOGGER_BLOG_ID in .env"],
            "tumblr": ["Create one app at tumblr.com/oauth/apps -> TUMBLR_CONSUMER_KEY/SECRET in .env -> run: python -m autowebpost.cli connect tumblr"],
            "mastodon": ["Preferences -> Development -> New Application (write:statuses, write:media) -> MASTODON_INSTANCE + MASTODON_TOKEN in .env"],
            "reddit": ["Create a script app at https://www.reddit.com/prefs/apps -> REDDIT_CLIENT_ID/SECRET + REDDIT_USERNAME/PASSWORD/SUBREDDIT in .env. Posting is public and heavily policed - read subreddit rules, post value, never bulk-link."],
            "writeas": ["Optional: create account -> WRITEAS_ALIAS + WRITEAS_PASSWORD in .env (anonymous posting also works)"],
            "githubpages": ["Create repo <user>.github.io -> Settings -> Pages -> enable -> create a fine-grained PAT with Contents read/write -> GITHUB_TOKEN + GITHUB_REPO in .env"],
            "telegraph": ["Nothing to register - telegra.ph needs no account. Token is created automatically on first post."],
            "hashnode": ["Settings -> Developer -> Personal Access Token (NOTE: API publishing now requires Hashnode Pro, $5/mo) -> HASHNODE_TOKEN + HASHNODE_PUBLICATION_ID"],
            "medium": ["Just sign up normally; posting is via 'Import a story' (no API since 2025)"],
        }
        return common + specific.get(site.slug, [f"Check {site.api_docs or site.url + '/docs'} for the API key location"])

    def register(self, slugs: List[str], open_browser: bool = False) -> List[SignupPlan]:
        plans = self.plan(slugs)
        for p in plans:
            self.vault.store_credential(p.site.slug, p.password, username=self.persona.email,
                                        note="generated for manual signup")
            self.vault.set_status(p.site.slug, "planned", "password generated; complete signup manually")
            if open_browser and p.site.signup_url:
                webbrowser.open(p.site.signup_url)
        return plans

    def mark(self, slug: str, status: str, detail: str = "") -> None:
        if status not in ("planned", "registered", "verified", "api-key-set", "skipped"):
            raise ValueError("status must be planned|registered|verified|api-key-set|skipped")
        self.vault.set_status(slug, status, detail)

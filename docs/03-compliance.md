# Rules of Engagement (read once, stay unbanned)

This project automates publishing through **official APIs** using **your accounts**.
That line matters: it is the difference between a content platform and a spam bot.

## What this tooling will and won't do

| Will do | Won't do |
|---|---|
| Generate signup plans + unique passwords for YOU to use | Auto-submit signup forms / solve CAPTCHAs |
| Publish via official APIs with your credentials | Scrape or script third-party web UIs |
| Post as drafts by default (you review before it's public) | Mass-post identical spam to many accounts |
| Set canonical URLs on syndicated copies | Fake authorship or invented credentials |

## Platform-specific notes

- **dev.to** — API key publishing allowed; 4 tags max; use canonical_url; front-page is tag-driven, don't tag-spam.
- **Medium** — no API; use Import (canonical) only; Partner Program requires disclosure of AI assistance per their rules.
- **Reddit** — not automated here on purpose. Manual participation, follow each subreddit's 9:1 self-promo ratio norms.
- **Tumblr / Blogger / WordPress** — one account each, complete profiles, human-paced posting.
- **Mastodon** — post value, not links-only; instance rules vary.
- **LinkedIn/Quora/Substack** — manual; adapt the snippet to the platform instead of cross-posting identical text.

## Disclosure

Google doesn't require labeling AI-assisted text, but several platforms and audiences do.
The engine adds an editorial-note disclosure by default — keep it. Honesty is a trust
signal, and trust is the center of E-E-A-T.

## Quality gate (enforced by design)

- Drafts ship with `EDIT-ME` markers and a review checklist.
- `publish` is a **dry run** unless you pass `--live`.
- API adapters create **drafts** where the platform supports it (dev.to, WP, Blogger, Hashnode).
- The queue's review window exists so a human decides what goes out.

If you scale: keep the human review step. Scaled content abuse is a spam policy violation
that gets entire domains demoted — automation should multiply your quality, not remove it.

# Research Report: Auto-Posting Tools & Free Publishing Platforms (August 2026)

This report summarizes the web research behind Auto-AI-WebPost's design decisions.

## 1. Reference auto-posting products

| Tool | Model | Free? | Platforms | Lesson we took |
|---|---|---|---|---|
| **Postiz** | Open source (AGPL-3.0), self-hosted + paid cloud | Free self-hosted | 30+ networks (Reddit, Discord, Mastodon, dev.to...) | Self-hosting + open source = $0 at any volume; AI image generation is now table-stakes |
| **Mixpost** | Open source core (Lite free), Pro one-time license | Lite free (3 networks) | 12 networks | Approval workflows matter — publishing without review is how accounts die |
| **Buffer / Publer / Metricool** | Hosted SaaS | Free tiers (1–3 channels) | 6–10+ | Hosted free tiers are too small for a content pipeline; they are for testing |
| **Hootsuite / Later** | Paid SaaS | Trials only | 20+ | Not relevant for a zero-budget workflow |

Sources: mixpost.app comparison of open-source social tools (2026); posteverywhere.ai Postiz-alternatives comparison (July 2026); socialk.it Mixpost alternatives (June 2026); openalternative.co listings (Postiz ≈34.4k stars, actively maintained).

**Conclusion:** a Python CLI + YAML queue + GitHub Actions scheduler gives the same capability set as Postiz/Mixpost for **$0**, with the content engine (SEO/E-E-A-T) those tools lack.

## 2. Free programmatic publishing channels (verified 2026)

| Platform | ~DA | Links | API status | Cost |
|---|---|---|---|---|
| GitHub Pages | 96 | dofollow | REST Contents API | free |
| Blogger | 96 | dofollow | API v3 (OAuth2) | free |
| Medium | 95 | nofollow | **API retired** — "Import a story" manual flow only | free |
| WordPress.com / self-hosted | 93 | dofollow | REST API + Application Passwords | free |
| Tumblr | 91 | dofollow | API v2 (OAuth1) | free |
| Mastodon | 90 | dofollow | REST API, app token | free |
| Telegra.ph | 88 | dofollow | Anonymous JSON API, **no account needed** | free |
| dev.to | 82 | nofollow | REST API, `api-key` header | free |
| Hashnode | 84 | dofollow | GraphQL — **moved behind Pro ($5/mo) in May 2026** | not free anymore |
| Write.as | 75 | dofollow | REST API, anonymous posting allowed | free |

Sources: nvarma.com blog-syndication pipeline writeup (Feb 2026) confirming dev.to REST + Hashnode GraphQL + Medium API removal; poster.ly Hashnode guide (2026) confirming the Pro paywall for the GraphQL API; theguidex.com web-2.0 authority list (March 2026); hnkmedia.com blog-submission directory (May 2026).

**Canonical-URL syndication** is the professional cross-posting pattern: publish once on your origin site, then syndicate with `canonical_url` pointing back — this is exactly what dev.to's `canonical_url` field and Medium's import flow are for, and it avoids duplicate-content de-duplication of the wrong page.

## 3. What Google rewards (E-E-A-T, 2026 state)

- Google does **not** penalize AI content for being AI content; it penalizes **low-value, mass-produced** content ("scaled content abuse"). Quality and E-E-A-T decide ranking.
- E-E-A-T = Experience, Expertise, Authoritativeness, Trust — Trust is the core; the other three feed it.
- Signals that matter, repeatedly confirmed across 2026 guides: verifiable author bios and credentials, first-hand experience, primary-source citations, structured data (Article, FAQ), consistent author entity across the web, transparent contact/corrections policy.
- AI Overviews cite from the same index with the same quality signals — "no special AI markup"; clear answers + E-E-A-T fundamentals are the cited-content pattern.
- Publishing unedited AI drafts at volume is the #1 way to get a site classified as scaled content abuse.

Sources: quickseo.ai 2026 AI-content guide (May 2026); stackmatix.com summary of Google Search Central AI Overviews guidance (Aug 2026); trackmyvisibility.com E-E-A-T guidelines (June 2026); flowninja.com SEO + AI do's/don'ts; seo.ai on the helpful-content wording change.

## 4. Free AI generation

- **Text:** Pollinations.ai — free, keyless, OpenAI-compatible endpoint (rate-limited; anonymous tier throttled under load). Any OpenAI-compatible provider (OpenAI, OpenRouter, Groq, local Ollama) plugs into the same interface.
- **Images:** Pollinations image endpoint (`image.pollinations.ai/prompt/...`) — free, keyless, Flux model, possible watermark + ~1 request/15s anonymous cap. Fine for a drip workflow; swap in any paid generator later without code changes.

Sources: tooljunction.io Pollinations review (2026); hiapi.ai free-image-API analysis (June 2026); pollinations API docs.

## 5. Anti-patterns this project refuses (and why)

- **Automated account registration / CAPTCHA solving / fake personas at scale** — violates the ToS of essentially every platform; accounts + domain get banned; undoes SEO. One account per site, created by a human (the register assistant prepares everything), posting via official API.
- **Blind posting of unedited AI text** — scaled-content-abuse risk; the pipeline bakes in a review gate (EDIT-ME markers refuse to be missed).
- **Webboard/forum spam** — link drops in forums get removed and flagged; the catalog only contains real publishing platforms with APIs or established manual flows.

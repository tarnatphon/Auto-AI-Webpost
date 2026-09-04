# Auto-AI-WebPost ⚡

**AI content engine + free multi-platform auto-publisher.** Generate SEO/E-E-A-T-optimized articles with AI images, review them, then auto-publish to high-authority websites through their official free APIs — scheduled from your Mac or free in the cloud via GitHub Actions.

```
                    ┌──────────────────────────────────────────────┐
                    │                YOUR PIPELINE                 │
                    │                                              │
  research ──▶ generate ──▶ images ──▶ ✍ REVIEW ──▶ queue ──▶ publish
  (keywords)  (AI draft,   (Flux,      (EDIT-ME      (drip     (official APIs,
              SEO+E-E-A-T)  free)       markers +     schedule)  dry-run default)
                                       checklist)
                    │
                    ▼
   ORIGIN: GitHub Pages / WordPress  ◀── canonical_url
                    │
        ┌───────────┼───────────┬─────────────┬───────────┐
        ▼           ▼           ▼             ▼           ▼
     dev.to     Blogger      Tumblr       Telegra.ph   Mastodon ... (+ Medium
   (DA 82)     (DA 96)      (DA 91)       (DA 88)      (DA 90)     import, manual)
```

## Why it's built this way

| Your requirement | How it works |
|---|---|
| 1. Reference auto-post tools from the web | Researched Postiz, Mixpost, Buffer et al. — [docs/01-research-report.md](docs/01-research-report.md) |
| 2. High-SEO / E-E-A-T content | Every article ships with author box, experience section, citations, FAQ + FAQPage/BlogPosting JSON-LD, key-takeaways box, disclosure — [docs/02-seo-eeat-playbook.md](docs/02-seo-eeat-playbook.md) |
| 3. Personal info + profile creation | One consistent persona (`data/persona.yaml`) + registration assistant: per-site signup plans, unique passwords, status tracking, `--open` opens signup pages in your browser |
| 4. High-quality, high-Google-visibility targets | Curated catalog of 15 free platforms, DA 67–96, with dofollow/nofollow + API status per site (`autowebpost sites`) |
| 5. 100% free | Every integrated API is free; AI text + images via keyless Pollinations; scheduling via GitHub Actions free tier |
| 6. Local Mac folder sync | `scripts/mac-setup.sh` + `scripts/sync_local.sh` for `/Volumes/AI/Auto AI WebPost` ⇄ GitHub ⇄ this repo |

**The origin-first pattern is the SEO core:** the canonical article lives on *your* site (GitHub Pages, free), and every syndicated copy points back via `canonical_url`. You get presence on DA 75–96 domains without duplicate-content problems — this is how professional publications cross-post.

## Quickstart (your Mac)

```bash
# 1. one-time setup of /Volumes/AI/Auto AI WebPost
bash scripts/mac-setup.sh
cd "/Volumes/AI/Auto AI WebPost" && source .venv/bin/activate

# 2. your identity (powers E-E-A-T + signup pre-fill)
python -m autowebpost.cli persona --init

# 3. see the free-platform catalog
python -m autowebpost.cli sites

# 4. prepare accounts (signup plans + passwords; you complete the forms)
python -m autowebpost.cli register githubpages devto telegraph --open

# 5. full pipeline: research -> draft -> (review) -> queue -> publish
python -m autowebpost.cli research "ai content automation" --expand
python -m autowebpost.cli generate --topic "Automating web publishing with AI" \
       --keyword "AI auto posting workflow" --references "https://source1;https://source2"
python -m autowebpost.cli publish output/drafts/<date-slug>/article.md --to telegraph,devto   # dry run
python -m autowebpost.cli publish output/drafts/<date-slug>/article.md --to telegraph,devto --live
```

Or one shot: `python -m autowebpost.cli run --topic "..." --to githubpages,devto,telegraph --wait 90`
(`--wait` is your human-review window before the queue fires.)

## Commands

| Command | What it does |
|---|---|
| `sites [--api-only]` | curated catalog: DA, dofollow, API status, per-site notes |
| `research KEYWORD [--expand]` | free long-tail + question keyword research (Google/DuckDuckGo autocomplete) |
| `persona [--init]` | create/show your author identity |
| `register SITE... [--open] [--list] [--mark slug:status]` | signup plans, password vault, status tracking |
| `generate --topic ...` | AI article draft + SEO meta + FAQ + E-E-A-T blocks + AI hero image |
| `publish DRAFT --to a,b [--live]` | publish via official APIs (**dry-run default**, drafts where supported) |
| `queue add/list/remove/run` | drip scheduler with stagger between platforms |
| `run --topic ... --wait N` | one-shot pipeline with review window |
| `serve [--host --port]` | local review dashboard: approve drafts before anything publishes |
| `connect tumblr` | one-time OAuth for Tumblr |

## Content engine

- **Providers:** `pollinations` (free, no key — default) · `openai` (any OpenAI-compatible endpoint: OpenAI, OpenRouter, Groq, Ollama, LM Studio) · `template` (offline scaffold, always works). Auto-falls back to template if the network provider fails.
- Force a provider for one run (or in CI) without editing `data/config.yaml`:

  ```bash
  AUTOWEBPOST_PROVIDER=template python -m autowebpost.cli generate --topic "..." --no-images
  ```

- **Images:** Flux via Pollinations (free, keyless), prompt-derived per article, with SEO alt text. Images are written to `<draft-folder>/images/` and referenced by **relative** path, so a draft stays portable between your Mac and CI.
- Every draft ships with `seo.jsonld.txt` (real `BlogPosting` + `FAQPage` structured data) and `review-checklist.md` — the 10-point E-E-A-T gate. `publish` refuses to feel safe until you've been through it.

## Free publishing targets (August 2026, researched)

Auto-post via API: **GitHub Pages** (DA 96, your origin) · **Blogger** (96) · **WordPress** (93) · **Tumblr** (91) · **Mastodon** (90) · **Telegra.ph** (88, no account needed) · **dev.to** (82) · **Write.as** (75) · Hashnode (API now Pro-only, flagged) · Medium (API retired — prepared manual-import flow). Catalog also covers LinkedIn, Substack, Quora, Reddit, LiveJournal, HubPages, Steemit, Google Sites with per-site strategy notes: `data/sites.yaml`.

## Safety model (why your accounts survive)

- Publishing only through **official APIs**, one account per site, created by **you** — the register assistant prepares forms and passwords but never auto-submits signups (ToS violation = platform-wide bans).
- **Dry-run by default**; adapters create **drafts** on platforms that support them; canonical URLs on every syndicated copy; disclosure note included; queue staggers platforms.
- See [docs/03-compliance.md](docs/03-compliance.md). Quality gate > volume: Google's scaled-content-abuse policy is the main risk to any auto-posting workflow, and the review step is what keeps you on the right side of it.

## Mac ⇄ GitHub sync (`/Volumes/AI/Auto AI WebPost`)

```bash
bash scripts/mac-setup.sh                        # once: clone/init + .venv + starter configs
bash scripts/sync_local.sh                       # anytime: pull --rebase, commit, push
# cron example (hourly):
# 30 * * * * bash "/Volumes/AI/Auto AI WebPost/scripts/sync_local.sh" >> "/Volumes/AI/Auto AI WebPost/.sync.log" 2>&1
```

## Cloud scheduling (free)

The workflow template lives at `.github/workflow-templates/autopost.yml` — `scripts/mac-setup.sh` copies it to `.github/workflows/` for you (GitHub only allows a logged-in user, not a bot, to create workflow files, so the push from your Mac is what activates it). It then runs your queue every 30 min on GitHub Actions' free tier. Add repo secrets for the platforms you use; keep `LIVE: "false"` until the pipeline is verified.

## Repo layout

```
autowebpost/          the engine (content, images, platforms, profiles, research,
                      scheduler, review, serve)
tests/                414 offline tests (pytest) - 94% coverage of autowebpost/
data/                 catalog (sites.yaml) + persona/config templates + .env.example
docs/                 research report · SEO/E-E-A-T playbook · compliance rules
scripts/              mac-setup.sh · sync_local.sh
output/drafts/        generated drafts + images + checklists (gitignored; example committed)
.github/workflows/    tests.yml (CI for this repo) · autopost.yml (free cloud scheduler)
```

## Review dashboard

The human-review gate, as an actual workflow instead of "remember to open the
markdown". Runs on the stdlib alone — no Flask, nothing new in `requirements.txt`.

```bash
python -m autowebpost.cli serve            # http://127.0.0.1:8765
python -m autowebpost.cli serve --allow-live --host 0.0.0.0   # only if you must
```

For each draft it shows the article preview, the SEO fields and generated
JSON-LD, every unresolved `EDIT-ME` marker, and the 10-point E-E-A-T checklist —
with the items it can verify itself marked *verified* (FAQ count, canonical URL,
meta length, keyword in title, images have alt text…) and the ones only you can
judge marked as yours. From there you approve or reject, add to the queue, or
publish.

The gates are enforced server-side, not just hidden in the UI:

- a draft must be **approved** before it can be published at all
- live publishing is off unless the server was started with `--allow-live`
- default bind is `127.0.0.1`, so it is not exposed to your network

Review state lives in `review.yaml` next to the article, so it travels with the
draft.

## Development

```bash
pip install -r requirements-dev.txt
pytest                                   # 414 tests, fully offline, ~5s
pytest --cov=autowebpost --cov-report=term-missing
```

The suite never touches the network or a real account. An autouse fixture in
`tests/conftest.py` **hard-blocks `requests`**, so a test cannot accidentally
publish: Telegra.ph needs no API key at all, so on a networked machine a stray
`live=True` would create a real public page. HTTP is mocked, the queue and draft
folders are redirected to `tmp_path`, and the live `_publish_live` path is
exercised with canned responses so adapter bugs surface before they reach your
accounts. CI (`.github/workflows/tests.yml`) runs the suite plus a CLI smoke
test on Python 3.9–3.13.

Install it as a package instead of running from a clone:

```bash
pip install -e .          # then: autowebpost sites
```

## Status of integrations (Aug 2026)

| Platform | Auto-publish | Notes |
|---|---|---|
| Telegra.ph | ✅ free, zero signup | instant pages, DA 88 |
| dev.to | ✅ free API key | drafts by default |
| WordPress (.com/self-hosted) | ✅ app password | drafts by default |
| GitHub Pages | ✅ PAT | your origin site |
| Blogger | ✅ OAuth2 token | drafts by default |
| Tumblr | ✅ OAuth1 (`connect tumblr`) | dofollow |
| Mastodon | ✅ app token | snippet + link |
| Write.as | ✅ optional account | anonymous OK |
| Hashnode | ⚠️ Pro now ($5/mo, May 2026) | adapter present, flagged |
| Medium | 🖐 prepared manual import | API retired 2025-26 |

## Changelog

### 2026-09-04 — review dashboard

`autowebpost serve`: a local web UI (stdlib `http.server`, no new dependencies)
that turns the human-review gate into a real workflow. Per draft: article
preview, SEO fields + JSON-LD, every unresolved `EDIT-ME` marker, and the
10-point E-E-A-T checklist with machine-verifiable items auto-checked. Approve /
reject / queue / publish from the same screen.

New `autowebpost/review.py` holds the judgement logic (state, marker detection,
auto-checks) with no HTTP in it, so it is testable in isolation. Gates are
enforced server-side: a draft must be approved before it can publish, live
publishing needs `--allow-live`, and the default bind is `127.0.0.1`.

### 2026-09-04 — hardening pass (+ test suite)

Bugs found by reading and running every code path, each now covered by a
regression test:

| Bug | Effect |
|---|---|
| `seo.jsonld.txt` was a 2-key stub | README promised `BlogPosting`/`FAQPage` JSON-LD per article; nothing was ever generated. Now real structured data, per schema type. |
| FAQ content destroyed on generate | The engine replaced the body's FAQ section with `<!-- faq-rendered-below -->` and never rendered it back — every published copy shipped an **empty FAQ** and lost the snippet content. |
| Images written to the wrong folder | Images went to `output/drafts/<slug>/images/` while the article went to `output/drafts/<date>-<slug>/`, so **every image reference was broken**. Images now land beside the article and use relative paths. |
| Telegraph `children` double-nested | Nodes were emitted as `[[...]]`; Telegraph only accepts a flat list, so live pages would have been rejected. |
| Local images sent to Telegraph | Only `output/`, `./` and `/` prefixes were filtered — relative `images/hero.jpg` shipped as a broken `<img>`. Any non-`http(s)` source is now dropped. |
| `--references` silently ignored | Unfilled `EDIT-ME` placeholders counted as "references present", so your real sources were dropped. Placeholders are filtered and your sources are rendered into the body. |
| `research` failed silently | Both suggestion sources failing printed an empty list and exited 0. Now reports the connectivity problem. |
| `generate` exited with status 1 | `sys.exit()` was handed a `Path`, so a **successful** run reported failure. Exit codes are now normalised. |
| One bad platform slug killed the queue | `run_due` raised `KeyError` and aborted the whole run; unknown slugs now fail just that entry. |
| `--wait 0` still queued | `"0"` is a truthy string, so the documented default queued for immediate publishing instead of not queueing. |
| Hero image alt text was the bare keyword | Alt text is now the author's `[IMAGE: ...]` description, or a descriptive phrase — not keyword stuffing. |
| `datetime.utcnow()` | Deprecated in 3.12+ and naive; replaced with a single timezone-aware helper. |

Also: `data/queue.yaml` parsing tolerates an empty/null file, `ImageAsset` ignores
unknown front-matter keys instead of making a draft unpublishable, and the
`register --list` hint no longer points at the command you just ran.

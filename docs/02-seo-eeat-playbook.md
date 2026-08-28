# The SEO / E-E-A-T Playbook (how this pipeline ranks)

Everything the content engine does maps to a documented Google quality signal.

## The 3-layer strategy

```
Layer 1  ORIGIN     your GitHub Pages / WordPress site - the canonical article
                    lives here, under your domain, with full schema markup
Layer 2  SYNDICATE  dev.to, Medium (import), Blogger, Tumblr, Write.as, Telegra.ph
                    each copy carries canonical_url -> origin. No duplicate-content
                    penalty, your entity appears on DA 75-96 domains
Layer 3  SOCIAL     Mastodon posts + LinkedIn/Quora manual snippets -> crawl discovery
                    + referral traffic + author-entity reinforcement
```

## What the engine injects into every article

| Block | Signal | Where |
|---|---|---|
| Author box w/ credentials + socials | Expertise, entity | end of article |
| "My experience with..." section w/ EDIT-ME marker | **Experience** (the first E) | mid-article — you fill it |
| Numbered references to primary sources | Trust | end of article |
| FAQ section (H3 questions) | Featured snippets / AI Overviews | end of article |
| FAQPage + BlogPosting JSON-LD | Structured data | origin site |
| AI-assistance + corrections disclosure | Trust / transparency | end of article |
| Descriptive alt text on original images | Accessibility + image SEO | inline |
| Key-takeaways box | Snippet bait, dwell time | top of article |
| Primary keyword: title / first 100 words / one H2 / meta | Classic on-page | everywhere |

## Before you publish (the 10-point checklist)

1. Every `<!-- EDIT-ME -->` marker replaced — no exceptions
2. Experience section contains something only YOU could write (numbers, tool names, mistakes)
3. Every statistic has a working citation
4. Facts spot-checked; `[VERIFY]` markers resolved
5. Meta description 120–158 chars, keyword + benefit
6. Title ≤ 60 chars, keyword front-loaded
7. FAQ answers real long-tail queries (run `autowebpost research --expand` if unsure)
8. Images: original, descriptive filenames + alt text
9. canonical_url set (origin URL) on every syndicated copy
10. Would you bookmark this if you found it via search? If not, don't publish

## Cadence beats volume

- 2–4 polished articles/week > 20 raw dumps/day. Google's scaled-content-abuse policy targets the latter.
- Stagger syndication (queue `--delay 30`): same-minute cross-posts look automated.
- Interlink your articles (topic clusters build topical authority — strongest play for a small site).
- Update old posts (freshness signal) instead of only adding new ones.

## Keyword workflow (free)

```bash
python -m autowebpost.cli research "ai auto posting" --expand
```
- `alphabet` output = long-tail title/H2 candidates
- `questions` output = your FAQ section, verbatim from real user queries
```
# pick keywords where you can add real experience; ignore anything you can't
```

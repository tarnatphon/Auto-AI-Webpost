"""Auto-AI-WebPost command line interface.

    python -m autowebpost.cli <command>

Run without arguments for the command list.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from .catalog import load_sites, sites_table
from .config import ROOT, load_config
from .content.eeat import eeat_qa_checklist
from .content.engine import Brief, ContentEngine, make_provider
from .platforms import get_many
from .profiles import RegistrationAssistant, Vault, load_persona
from .profiles.persona import bootstrap as bootstrap_persona
from .research.keywords import expand, suggest
from .scheduler import add as queue_add, entries as queue_entries, remove as queue_remove, run_due


def cmd_sites(args):
    sites = load_sites()
    if args.api_only:
        print(sites_table(sites, only_api=True))
    else:
        print(f"\nCurated catalog: {len(sites)} free, high-authority platforms (2026 research)\n")
        print(sites_table(sites))
        print("\nUse 'autowebpost register <slug>' to prepare an account on any of these.\n")


def cmd_research(args):
    print(f"\nKeyword research: {args.keyword}\n" + "=" * 50)
    if args.expand:
        data = expand(args.keyword)
        print("\nLONG-TAIL (alphabet expansion):")
        for s in data["alphabet"]:
            print("  -", s)
        print("\nQUESTION KEYWORDS (FAQ gold):")
        for s in data["questions"]:
            print("  -", s)
    else:
        for s in suggest(args.keyword):
            print("  -", s)
    print()


def cmd_persona(args):
    if args.init:
        answers = {
            "name": input("Real or pen name [Alex Carter]: ").strip() or "Alex Carter",
            "handle": input("Handle/username [alexcarter]: ").strip() or "alexcarter",
            "email": input("Contact email: ").strip(),
            "website": input("Website (origin site, e.g. https://user.github.io): ").strip(),
            "tagline": input("One-line tagline: ").strip(),
            "expertise": input("Expertise, comma separated [AI automation, SEO, Python]: ").strip() or "AI automation, SEO, Python",
            "credentials": input("Real credentials, comma separated (leave blank if none yet): ").strip(),
            "years": input("Years of hands-on experience [5]: ").strip() or "5",
            "social": {"github": input("GitHub URL: ").strip(), "x": input("X/Twitter URL: ").strip()},
        }
        p = bootstrap_persona(answers)
        print(f"\nPersona saved -> data/persona.yaml\n  {p.name} (@{p.handle}) - {p.tagline}")
    else:
        p = load_persona()
        print(f"\nPersona: {p.name} (@{p.handle})")
        print(f"  Brand: {p.brand}")
        print(f"  Expertise: {', '.join(p.expertise)}")
        print(f"  Bio: {p.bio_short}\n")


def cmd_register(args):
    vault = Vault()
    if args.list:
        print("\nREGISTRATION STATUS\n" + "=" * 50)
        print(vault.status_table(), "\n")
        return
    if args.mark:
        slug, _, status = args.mark.partition(":")
        vault.set_status(slug.strip(), status.strip() or "registered")
        print(f"Marked {slug} -> {status or 'registered'}")
        return
    persona = load_persona()
    assistant = RegistrationAssistant(persona, vault)
    slugs = args.sites or []
    if not slugs:
        print("\nNo sites given. Examples:\n  autowebpost register devto telegraph\n  autowebpost register --list\n")
        return
    plans = assistant.register(slugs, open_browser=args.open)
    print("\nSIGNUP PLANS generated (passwords saved to data/.credentials.local.yaml - gitignored)\n")
    print("IMPORTANT: you complete each signup yourself. Automated account creation violates")
    print("platform ToS and gets everything banned. One account per site, via official APIs.\n")
    for p in plans:
        print(f"=== {p.site.name} ({p.site.url})  ~DA {p.site.da}  link: {'dofollow' if p.site.dofollow else 'nofollow'} ===")
        for i, s in enumerate(p.steps, 1):
            print(f"  {i}. {s}")
        print("  Fields to use:")
        for k, v in p.fields.items():
            if v:
                print(f"     - {k}: {v}")
        print(f"  Suggested password: {p.password}\n")


def cmd_generate(args):
    cfg = load_config()
    persona = load_persona()
    provider = make_provider(cfg.get("content", {}))
    print(f"\nGenerating draft  |  provider: {provider.name}  |  persona: {persona.name}")
    print(f"Topic: {args.topic}")
    if provider.name == "template":
        print("(offline template - fill the EDIT-ME markers, or set provider: pollinations in data/config.yaml)")
    engine = ContentEngine(persona, provider)
    refs = [r.strip() for r in (args.references or "").split(";") if r.strip()]
    brief = Brief(
        topic=args.topic,
        primary_keyword=args.keyword or args.topic,
        secondary_keywords=[s.strip() for s in (args.secondary or "").split(",") if s.strip()],
        angle=args.angle,
        word_target=args.words,
        references=refs,
    )
    draft = engine.generate(brief, generate_images=not args.no_images)
    folder = ROOT / "output" / "drafts" / (datetime.utcnow().date().isoformat() + "-" + draft.slug)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "article.md"
    path.write_text(draft.to_markdown(), encoding="utf-8")

    # side-car files that platforms ingest separately
    (folder / "seo.jsonld.txt").write_text(
        json.dumps({"article": draft.meta_description, "title": draft.title}, indent=2), encoding="utf-8")
    (folder / "review-checklist.md").write_text(
        "# E-E-A-T review checklist (do this BEFORE publishing)\n\n"
        + "\n".join(f"- [ ] {c}" for c in eeat_qa_checklist()), encoding="utf-8")

    print(f"\nDraft written -> {path}")
    print(f"  title : {draft.title}")
    print(f"  slug  : {draft.slug}")
    print(f"  meta  : {draft.meta_description}")
    print(f"  tags  : {', '.join(draft.tags)}")
    print(f"  images: {len(draft.images)} generated" if draft.images else "  images: none (use --no-images? they may have failed)")
    print(f"  faq   : {len(draft.faq)} questions | words: {len(draft.body_markdown.split())}")
    print(f"\nNext:\n  1. Edit the draft (remove every EDIT-ME marker)")
    print(f"  2. python -m autowebpost.cli publish {path} --to telegraph,devto   (dry run)")
    print(f"  3. add --live when the checklist passes\n")
    return path


def cmd_publish(args):
    from .models import ArticleDraft
    draft = ArticleDraft.load(args.draft)
    persona = load_persona()
    platforms = get_many(args.to)
    if not draft.canonical_url:
        print("NOTE: draft has no canonical_url. If cross-posting, publish to your ORIGIN")
        print("      (githubpages/wordpress) first, then set canonical_url and syndicate.\n")
    n_live = 0
    for pub in platforms:
        print(f"\n--- {pub.name} " + "-" * (40 - len(pub.name)))
        result = pub.publish(draft, persona, live=args.live)
        print(result)
        if args.live and result.ok and not result.dry_run:
            n_live += 1
    mode = "LIVE" if args.live else "DRY-RUN (add --live to actually publish)"
    print(f"\nDone ({mode}): {n_live}/{len(platforms)} posted live.\n")
    if not args.live:
        print("Publishing flow: origin first (githubpages/wordpress) -> set canonical_url -> syndicate.")
        print("Review every platform's draft queue before it goes public. Quality > volume.\n")


def cmd_queue(args):
    if args.cmd == "add":
        e = queue_add(args.draft, [p.strip() for p in args.platforms.split(",")], args.at,
                      delay_minutes=args.delay)
        print(f"Queued {e['id']}: {args.draft} -> {args.platforms} at {e['publish_at']}")
    elif args.cmd == "list":
        for e in queue_entries():
            print(f"[{e['status']:9}] {e['id']}  {e['publish_at']}  {Path(e['draft']).parent.name}  -> {','.join(e['platforms'])}")
        if not queue_entries():
            print("Queue is empty.")
    elif args.cmd == "remove":
        print("Removed." if queue_remove(args.id) else "Not found.")
    elif args.cmd == "run":
        done = run_due(live=args.live)
        if not done:
            print("Nothing due.")
        for e in done:
            print(f"[{e['status']}] {e['draft']}")
            for r in e.get("results", []):
                print(f"   - {r.get('platform')}: {'OK ' if r.get('ok') else 'FAIL'} {r.get('url') or r.get('detail') or r.get('note', '')}")


def cmd_run(args):
    """One-shot: research -> generate -> (review gate) -> publish -> queue syndication."""
    args.keyword = args.keyword or args.topic
    args.secondary, args.angle, args.words = "", "practical, experience-based how-to", 1400
    args.references, args.no_images = "", False
    path = cmd_generate(args)
    if args.wait:
        when = (datetime.utcnow() + timedelta(minutes=int(args.wait))).strftime("%Y-%m-%d %H:%M")
        queue_add(str(path), [p.strip() for p in args.to.split(",")], when)
        print(f"Queued for {when} -> platforms: {args.to}")
        print("The wait is your HUMAN REVIEW window. The queue will not fix bad content for you.")


def cmd_connect(args):
    if args.service == "tumblr":
        from .platforms.tumblr import run_connect_flow
        run_connect_flow()
    else:
        print("Available: tumblr")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="autowebpost",
                                 description="AI content engine + free multi-platform auto-publisher (official APIs only)")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("sites", help="list the curated free-platform catalog")
    s.add_argument("--api-only", action="store_true")
    s.set_defaults(fn=cmd_sites)

    s = sub.add_parser("research", help="free keyword research (Google/DuckDuckGo autocomplete)")
    s.add_argument("keyword")
    s.add_argument("--expand", action="store_true", help="long-tail + question expansion")
    s.set_defaults(fn=cmd_research)

    s = sub.add_parser("persona", help="show or create your author persona")
    s.add_argument("--init", action="store_true")
    s.set_defaults(fn=cmd_persona)

    s = sub.add_parser("register", help="signup plans + password vault + status tracking")
    s.add_argument("sites", nargs="*")
    s.add_argument("--list", action="store_true")
    s.add_argument("--open", action="store_true", help="open signup pages in your browser")
    s.add_argument("--mark", help="slug:status (planned|registered|verified|api-key-set)")
    s.set_defaults(fn=cmd_register)

    s = sub.add_parser("generate", help="generate an SEO/E-E-A-T article draft")
    s.add_argument("--topic", required=True)
    s.add_argument("--keyword", help="primary keyword (default: topic)")
    s.add_argument("--secondary", help="comma separated secondary keywords")
    s.add_argument("--angle", default="practical, experience-based how-to")
    s.add_argument("--words", type=int, default=1400)
    s.add_argument("--references", help="semicolon separated source URLs")
    s.add_argument("--no-images", action="store_true")
    s.set_defaults(fn=cmd_generate)

    s = sub.add_parser("publish", help="publish a draft to platforms (DRY RUN by default)")
    s.add_argument("draft")
    s.add_argument("--to", required=True, help="comma separated: telegraph,devto,wordpress,githubpages,blogger,tumblr,mastodon,writeas,hashnode,medium")
    s.add_argument("--live", action="store_true")
    s.set_defaults(fn=cmd_publish)

    q = sub.add_parser("queue", help="drip queue: add/list/remove/run")
    q.add_argument("cmd", choices=["add", "list", "remove", "run"])
    q.add_argument("draft", nargs="?")
    q.add_argument("--platforms", default="telegraph")
    q.add_argument("--at", default="", help='"YYYY-MM-DD HH:MM" (UTC)')
    q.add_argument("--id")
    q.add_argument("--delay", type=int, default=0, help="minutes between platforms")
    q.add_argument("--live", action="store_true")
    q.set_defaults(fn=cmd_queue)

    s = sub.add_parser("run", help="one-shot: generate now, queue syndication after review window")
    s.add_argument("--topic", required=True)
    s.add_argument("--keyword")
    s.add_argument("--to", default="githubpages,devto,telegraph,mastodon")
    s.add_argument("--wait", default="0", help="minutes until queued publish (your review window)")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("connect", help="one-time OAuth connection for a platform")
    s.add_argument("service", choices=["tumblr"])
    s.set_defaults(fn=cmd_connect)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 0
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())

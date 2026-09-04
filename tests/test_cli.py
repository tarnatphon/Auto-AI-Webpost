"""End-to-end CLI: the commands a user actually types.

All runs are offline and write only into tmp_path.
"""
from __future__ import annotations

import json
import re

import pytest

from autowebpost.cli import main


@pytest.fixture(autouse=True)
def offline_and_temp(monkeypatch, tmp_path):
    """Force the offline provider and redirect drafts/queue away from the repo."""
    import autowebpost.cli as cli_mod
    import autowebpost.drafts as drafts_mod
    from autowebpost.content.engine import TemplateProvider

    monkeypatch.setattr(cli_mod, "make_provider", lambda cfg: TemplateProvider())
    monkeypatch.setattr(drafts_mod, "OUTPUT_DIR", tmp_path / "output")
    return tmp_path


def run(*argv):
    return main(list(argv))


class TestSites:
    def test_lists_the_catalog(self, capsys):
        run("sites")
        out = capsys.readouterr().out
        assert "devto" in out and "telegraph" in out

    def test_api_only(self, capsys):
        run("sites", "--api-only")
        out = capsys.readouterr().out
        assert "telegraph" in out
        assert "linkedin" not in out


class TestPersona:
    def test_shows_the_persona(self, capsys):
        run("persona")
        out = capsys.readouterr().out
        assert "Persona:" in out and "Alex Carter" in out


class TestRegister:
    def test_list_reports_empty_state_with_a_usable_hint(self, capsys, monkeypatch, tmp_path):
        import autowebpost.profiles.vault as vault_mod
        monkeypatch.setattr(vault_mod, "STATUS_FILE", tmp_path / "status.yaml")
        run("register", "--list")
        out = capsys.readouterr().out
        assert "No registrations tracked" in out
        # Regression: the hint used to point at the very command you just ran.
        assert "register --list" not in out

    def test_list_shows_marked_statuses(self, capsys, monkeypatch, tmp_path):
        import autowebpost.profiles.vault as vault_mod
        monkeypatch.setattr(vault_mod, "STATUS_FILE", tmp_path / "status.yaml")
        vault_mod.Vault().set_status("devto", "api-key-set", "key added")
        run("register", "--list")
        out = capsys.readouterr().out
        assert "devto" in out and "api-key-set" in out

    def test_mark_defaults_to_registered(self, capsys, monkeypatch, tmp_path):
        import autowebpost.profiles.vault as vault_mod
        monkeypatch.setattr(vault_mod, "STATUS_FILE", tmp_path / "status.yaml")
        run("register", "--mark", "devto:")
        out = capsys.readouterr().out
        assert "devto -> registered" in out
        assert vault_mod.Vault().all_status()["devto"]["status"] == "registered"

    def test_creates_a_signup_plan(self, capsys, monkeypatch, tmp_path):
        import autowebpost.profiles.vault as vault_mod
        monkeypatch.setattr(vault_mod, "CRED_FILE", tmp_path / "creds.yaml")
        monkeypatch.setattr(vault_mod, "STATUS_FILE", tmp_path / "status.yaml")
        run("register", "devto", "telegraph")
        out = capsys.readouterr().out
        assert "DEV.to" in out
        assert "You complete each signup yourself" in out or "you complete" in out.lower()

    def test_no_sites_prints_usage(self, capsys):
        run("register")
        assert "No sites given" in capsys.readouterr().out


class TestGenerate:
    def test_writes_the_draft_and_sidecars(self, capsys, tmp_path):
        rc = run("generate", "--topic", "Automating web publishing with AI",
                 "--keyword", "AI auto posting workflow", "--no-images")
        assert rc == 0
        folders = list((tmp_path / "output" / "drafts").iterdir())
        assert len(folders) == 1
        for name in ("article.md", "seo.jsonld.txt", "review-checklist.md"):
            assert (folders[0] / name).exists()

    def test_folder_is_dated_and_slugged(self, tmp_path):
        run("generate", "--topic", "Test Topic Here", "--no-images")
        name = (tmp_path / "output" / "drafts").iterdir().__next__().name
        assert re.match(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$", name)

    def test_seo_sidecar_contains_real_structured_data(self, tmp_path):
        """Regression: this used to be a two-key stub instead of JSON-LD."""
        run("generate", "--topic", "Test Topic Here", "--no-images")
        folder = next((tmp_path / "output" / "drafts").iterdir())
        blob = (folder / "seo.jsonld.txt").read_text(encoding="utf-8")
        blocks = [b.strip() for b in re.split(r"^<!--.*?-->\s*$", blob, flags=re.M) if b.strip()]
        types = {json.loads(b)["@type"] for b in blocks}
        assert types == {"BlogPosting", "FAQPage"}

    def test_references_reach_the_article_and_the_draft(self, tmp_path):
        run("generate", "--topic", "Test Topic Here", "--no-images",
            "--references", "https://example.com/a;https://example.com/b")
        folder = next((tmp_path / "output" / "drafts").iterdir())
        from autowebpost.models import ArticleDraft
        d = ArticleDraft.load(folder / "article.md")
        assert d.references == ["https://example.com/a", "https://example.com/b"]
        assert "https://example.com/a" in d.body_markdown

    def test_faq_survives_into_the_published_body(self, tmp_path):
        run("generate", "--topic", "Test Topic Here", "--no-images")
        folder = next((tmp_path / "output" / "drafts").iterdir())
        from autowebpost.models import ArticleDraft
        d = ArticleDraft.load(folder / "article.md")
        assert d.faq
        for item in d.faq:
            assert item.question in d.body_markdown
            assert item.answer in d.body_markdown

    def test_prints_the_next_steps(self, capsys, tmp_path):
        run("generate", "--topic", "Test Topic Here", "--no-images")
        out = capsys.readouterr().out
        assert "publish" in out and "--live" in out


class TestPublish:
    def test_dry_run_is_the_default_and_publishes_nothing(self, capsys, tmp_path, draft, persona):
        from autowebpost.drafts import save_draft
        folder = save_draft(draft, persona, folder=tmp_path / "d")
        run("publish", str(folder / "article.md"), "--to", "telegraph,devto")
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "0/2 posted live" in out

    def test_warns_when_there_is_no_canonical_url(self, capsys, tmp_path, minimal_draft, persona):
        from autowebpost.drafts import save_draft
        folder = save_draft(minimal_draft, persona, folder=tmp_path / "d")
        run("publish", str(folder / "article.md"), "--to", "devto")
        assert "canonical_url" in capsys.readouterr().out

    def test_unknown_platform_raises(self, tmp_path, draft, persona):
        from autowebpost.drafts import save_draft
        folder = save_draft(draft, persona, folder=tmp_path / "d")
        with pytest.raises(KeyError):
            run("publish", str(folder / "article.md"), "--to", "myspace")


class TestQueue:
    def test_add_then_list_then_remove(self, capsys, monkeypatch, tmp_path):
        import autowebpost.scheduler as sched
        monkeypatch.setattr(sched, "QUEUE_FILE", tmp_path / "queue.yaml")
        from autowebpost.models import ArticleDraft, Persona
        from autowebpost.drafts import save_draft
        folder = save_draft(ArticleDraft(title="T", slug="t", body_markdown="b"),
                            Persona(), folder=tmp_path / "d")

        run("queue", "add", str(folder / "article.md"),
            "--platforms", "telegraph,devto", "--at", "2030-01-01 09:00")
        out = capsys.readouterr().out
        assert "Queued" in out

        run("queue", "list")
        out = capsys.readouterr().out
        assert "telegraph,devto" in out and "pending" in out

        entry_id = sched.entries()[0]["id"]
        run("queue", "remove", "--id", entry_id)
        assert "Removed" in capsys.readouterr().out

    def test_list_on_an_empty_queue(self, capsys, monkeypatch, tmp_path):
        import autowebpost.scheduler as sched
        monkeypatch.setattr(sched, "QUEUE_FILE", tmp_path / "queue.yaml")
        run("queue", "list")
        assert "Queue is empty" in capsys.readouterr().out

    def test_run_nothing_due(self, capsys, monkeypatch, tmp_path):
        import autowebpost.scheduler as sched
        monkeypatch.setattr(sched, "QUEUE_FILE", tmp_path / "queue.yaml")
        run("queue", "run")
        assert "Nothing due" in capsys.readouterr().out


class TestResearch:
    def test_reports_failure_instead_of_printing_nothing(self, capsys, monkeypatch):
        """Regression: both sources failing printed an empty list and exit 0."""
        import autowebpost.cli as cli_mod
        monkeypatch.setattr(cli_mod, "suggest", lambda k: [])
        monkeypatch.setattr(cli_mod, "expand",
                            lambda k: {"seed": k, "alphabet": [], "questions": []})
        run("research", "ai content automation")
        out = capsys.readouterr().out
        assert "no suggestions" in out
        assert "connection" in out.lower()

    def test_prints_suggestions_when_available(self, capsys, monkeypatch):
        import autowebpost.cli as cli_mod
        monkeypatch.setattr(cli_mod, "suggest", lambda k: ["ai content workflow", "ai tools"])
        run("research", "ai content")
        out = capsys.readouterr().out
        assert "ai content workflow" in out and "ai tools" in out

    def test_expand_prints_both_sections(self, capsys, monkeypatch):
        import autowebpost.cli as cli_mod
        monkeypatch.setattr(cli_mod, "expand", lambda k: {
            "seed": k, "alphabet": ["a"], "questions": ["how to a"]})
        run("research", "ai content", "--expand")
        out = capsys.readouterr().out
        assert "LONG-TAIL" in out and "QUESTION KEYWORDS" in out
        assert "how to a" in out


class TestRun:
    def test_generates_and_queues(self, capsys, monkeypatch, tmp_path):
        import autowebpost.scheduler as sched
        monkeypatch.setattr(sched, "QUEUE_FILE", tmp_path / "queue.yaml")
        run("run", "--topic", "Test Topic Here", "--to", "telegraph", "--wait", "60")
        out = capsys.readouterr().out
        assert "Queued for" in out
        assert len(sched.entries()) == 1

    def test_no_wait_means_no_queue_entry(self, monkeypatch, tmp_path):
        import autowebpost.scheduler as sched
        monkeypatch.setattr(sched, "QUEUE_FILE", tmp_path / "queue.yaml")
        run("run", "--topic", "Test Topic Here", "--to", "telegraph", "--wait", "0")
        assert sched.entries() == []


class TestEntryPoint:
    def test_no_args_prints_help(self, capsys):
        assert run() == 0
        assert "usage" in capsys.readouterr().out.lower()

    def test_version(self, capsys):
        from autowebpost import __version__
        with pytest.raises(SystemExit) as e:
            run("--version")
        assert e.value.code == 0
        assert __version__ in capsys.readouterr().out

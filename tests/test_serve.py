"""The dashboard HTTP surface.

The server runs on an ephemeral loopback port and is driven with urllib, so the
whole request/response path is exercised for real. (urllib rather than requests
because the test suite blocks `requests` outright - see conftest.)
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.client import HTTPException

import pytest

from autowebpost.drafts import save_draft
from autowebpost.models import ArticleDraft
from autowebpost.review import STATUS_APPROVED, set_decision
from autowebpost.serve import Dashboard, create_server

MARKER = "<!-- EDIT-ME: fill this in -->"


def draft(**kw):
    base = dict(title="A Draft", slug="a-draft", primary_keyword="kw",
                meta_description="m" * 130, body_markdown=f"body {MARKER}",
                faq=[], references=[], images=[], canonical_url="")
    base.update(kw)
    return ArticleDraft(**base)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A live dashboard bound to 127.0.0.1 on a free port."""
    import autowebpost.scheduler as sched
    monkeypatch.setattr(sched, "QUEUE_FILE", tmp_path / "queue.yaml")

    server = create_server(host="127.0.0.1", port=0, allow_live=False,
                           drafts_dir=tmp_path)
    port = server.server_address[1]
    thread = threading.Thread(target=lambda: server.serve_forever(0.05),
                              daemon=True)
    thread.start()

    class Client:
        base = f"http://127.0.0.1:{port}"

        def _req(self, path, method="GET", payload=None):
            data = json.dumps(payload).encode() if payload is not None else None
            req = urllib.request.Request(self.base + path, data=data, method=method)
            if data:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    raw = r.read()
                    ctype = r.headers.get("Content-Type", "")
                    return r.status, ctype, raw
            except urllib.error.HTTPError as e:
                return e.code, e.headers.get("Content-Type", ""), e.read()

        def get(self, path):
            code, ctype, raw = self._req(path)
            return code, ctype, raw

        def json(self, path):
            code, _, raw = self._req(path)
            return code, (json.loads(raw) if raw else None)

        def post(self, path, payload):
            code, _, raw = self._req(path, "POST", payload)
            return code, (json.loads(raw) if raw else None)

        def delete(self, path):
            return self._req(path, "DELETE")[0]

    yield Client(), tmp_path
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture
def seeded(client, persona):
    c, root = client
    folder = save_draft(draft(), persona, folder=root / "2026-09-04-a-draft")
    return c, root, folder


class TestIndex:
    def test_serves_the_single_page_app(self, client):
        c, _ = client
        code, ctype, raw = c.get("/")
        assert code == 200
        assert "text/html" in ctype
        assert b"Auto-AI-WebPost" in raw

    def test_unknown_route_is_404(self, client):
        c, _ = client
        assert c.json("/api/nope")[0] == 404


class TestStatus:
    def test_reports_the_environment(self, client):
        c, _ = client
        code, body = c.json("/api/status")
        assert code == 200
        assert body["allow_live"] is False
        assert body["persona"]
        assert "telegraph" in body["platforms"]
        assert body["queue_count"] == 0

    def test_reports_allow_live_when_enabled(self, tmp_path):
        server = create_server("127.0.0.1", 0, allow_live=True, drafts_dir=tmp_path)
        try:
            assert server.RequestHandlerClass.dashboard.allow_live is True
        finally:
            server.server_close()


class TestDrafts:
    def test_empty_at_first(self, client):
        c, _ = client
        code, body = c.json("/api/drafts")
        assert code == 200 and body == []

    def test_lists_a_draft(self, seeded):
        c, _, _ = seeded
        code, body = c.json("/api/drafts")
        assert code == 200 and len(body) == 1
        assert body[0]["title"] == "A Draft"
        assert body[0]["status"] == "pending"
        assert body[0]["marker_count"] == 1

    def test_detail_includes_rendered_html_and_schema(self, seeded):
        c, _, folder = seeded
        code, body = c.json("/api/drafts/2026-09-04-a-draft")
        assert code == 200
        assert "<p>" in body["html"]
        assert "BlogPosting" in body["jsonld"]
        assert "title: A Draft" in body["front_matter"]
        assert len(body["checklist"]) == 10

    def test_detail_escapes_article_markup(self, seeded):
        """The preview must not let article text inject markup into the page."""
        c, _, folder = seeded
        (folder / "article.md").write_text(
            "---\ntitle: T\nslug: t\n---\n\n<script>alert(1)</script>\n", encoding="utf-8")
        code, body = c.json("/api/drafts/2026-09-04-a-draft")
        assert "<script>" not in body["html"]

    def test_unknown_draft_is_404(self, client):
        c, _ = client
        assert c.json("/api/drafts/does-not-exist")[0] == 404


class TestTraversal:
    @pytest.mark.parametrize("bad", [
        "../../data", "..", "/etc", "..%2f..%2fdata", "....//....//data",
    ])
    def test_cannot_escape_the_drafts_dir(self, client, bad):
        c, _ = client
        code, _ = c.json("/api/drafts/" + bad)
        assert code == 404

    def test_folder_for_rejects_traversal(self, tmp_path):
        d = Dashboard(drafts_dir=tmp_path)
        for bad in ("../x", "..", "a/b", "", ".", "\\x"):
            with pytest.raises(LookupError):
                d.folder_for(bad)

    def test_folder_for_accepts_a_real_draft(self, tmp_path):
        (tmp_path / "real").mkdir()
        assert Dashboard(drafts_dir=tmp_path).folder_for("real") == (tmp_path / "real").resolve()


class TestDecisions:
    def test_approve_then_publishable(self, seeded):
        c, _, _ = seeded
        code, body = c.post("/api/drafts/2026-09-04-a-draft/decision",
                            {"status": "approved"})
        assert code == 200 and body["status"] == "approved"
        assert body["summary"]["publishable"] is True

    def test_reject_then_not_publishable(self, seeded):
        c, _, _ = seeded
        code, body = c.post("/api/drafts/2026-09-04-a-draft/decision",
                            {"status": "rejected"})
        assert code == 200 and body["summary"]["publishable"] is False

    def test_invalid_status_is_400(self, seeded):
        c, _, _ = seeded
        code, body = c.post("/api/drafts/2026-09-04-a-draft/decision",
                            {"status": "maybe"})
        assert code == 400 and "error" in body

    def test_decision_persists(self, seeded):
        c, _, folder = seeded
        c.post("/api/drafts/2026-09-04-a-draft/decision", {"status": "approved"})
        _, body = c.json("/api/drafts/2026-09-04-a-draft")
        assert body["status"] == "approved"

    def test_checklist_toggle(self, seeded):
        c, _, _ = seeded
        item = "Numbers/dates fact-checked against references (Trust)"
        code, body = c.post("/api/drafts/2026-09-04-a-draft/checklist",
                            {"item": item, "done": True})
        assert code == 200 and body["checklist"][item] is True

    def test_notes(self, seeded):
        c, _, _ = seeded
        code, body = c.post("/api/drafts/2026-09-04-a-draft/notes",
                            {"notes": "needs a better hook"})
        assert code == 200 and body["notes"] == "needs a better hook"


class TestPublishGate:
    def test_unapproved_draft_is_refused(self, seeded):
        c, _, _ = seeded
        code, body = c.post("/api/publish", {"draft": "2026-09-04-a-draft",
                                             "platforms": ["devto"], "live": False})
        assert code == 403 and "not approved" in body["error"]

    def test_approved_draft_dry_runs(self, seeded):
        c, _, folder = seeded
        set_decision(folder, STATUS_APPROVED)
        code, body = c.post("/api/publish", {"draft": "2026-09-04-a-draft",
                                             "platforms": ["devto", "wordpress"],
                                             "live": False})
        assert code == 200
        assert [r["platform"] for r in body["results"]] == ["devto", "wordpress"]
        assert all(r["dry_run"] for r in body["results"])

    def test_live_is_refused_without_allow_live(self, seeded):
        c, _, folder = seeded
        set_decision(folder, STATUS_APPROVED)
        code, body = c.post("/api/publish", {"draft": "2026-09-04-a-draft",
                                             "platforms": ["devto"], "live": True})
        assert code == 403 and "--allow-live" in body["error"]

    def test_unknown_platform_is_400(self, seeded):
        c, _, folder = seeded
        set_decision(folder, STATUS_APPROVED)
        code, _ = c.post("/api/publish", {"draft": "2026-09-04-a-draft",
                                          "platforms": ["myspace"], "live": False})
        assert code == 400

    def test_unknown_draft_is_404(self, client):
        c, _ = client
        code, _ = c.post("/api/publish", {"draft": "nope",
                                          "platforms": ["devto"], "live": False})
        assert code == 404


class TestAllowLive:
    @pytest.fixture
    def live_client(self, tmp_path, monkeypatch):
        import autowebpost.serve as serve_mod

        class FakeResult:
            def __init__(self, slug):
                self.ok, self.url, self.detail, self.dry_run = (
                    True, f"https://example.com/{slug}", "posted live", False)

        class FakePublisher:
            def __init__(self, slug):
                self.slug, self.name = slug, slug

            def publish(self, d, p, live=False):
                FakePublisher.calls.append((self.slug, live))
                return FakeResult(self.slug)

        FakePublisher.calls = []
        monkeypatch.setattr(serve_mod, "get_many",
                            lambda names: [FakePublisher(n) for n in names])

        server = create_server("127.0.0.1", 0, allow_live=True, drafts_dir=tmp_path)
        port = server.server_address[1]
        t = threading.Thread(target=lambda: server.serve_forever(0.05),
                              daemon=True)
        t.start()
        try:
            yield port, FakePublisher
        finally:
            server.shutdown(); server.server_close(); t.join(timeout=5)

    def _post(self, port, payload):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/publish",
                                     data=json.dumps(payload).encode(),
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_live_publish_reaches_the_adapter(self, live_client, tmp_path, persona):
        port, Fake = live_client
        folder = save_draft(draft(), persona, folder=tmp_path / "2026-09-04-a-draft")
        set_decision(folder, STATUS_APPROVED)

        code, body = self._post(port, {"draft": "2026-09-04-a-draft",
                                       "platforms": ["devto"], "live": True})
        assert code == 200
        assert Fake.calls == [("devto", True)]
        assert body["results"][0]["url"] == "https://example.com/devto"

    def test_still_requires_approval(self, live_client, tmp_path, persona):
        port, Fake = live_client
        save_draft(draft(), persona, folder=tmp_path / "2026-09-04-a-draft")
        code, body = self._post(port, {"draft": "2026-09-04-a-draft",
                                       "platforms": ["devto"], "live": True})
        assert code == 403 and Fake.calls == []


class TestQueue:
    def test_add_then_list_then_remove(self, seeded):
        c, _, _ = seeded
        code, entry = c.post("/api/queue", {"draft": "2026-09-04-a-draft",
                                            "platforms": ["telegraph", "devto"],
                                            "at": "2030-01-01 09:00", "delay": 30})
        assert code == 200
        assert entry["platforms"] == ["telegraph", "devto"]
        assert entry["delay_minutes"] == 30

        _, listing = c.json("/api/queue")
        assert [e["id"] for e in listing] == [entry["id"]]

        assert c.delete("/api/queue/" + entry["id"]) == 200
        _, listing = c.json("/api/queue")
        assert listing == []

    def test_removing_an_unknown_entry_reports_false(self, client):
        c, _ = client
        code, body = c._req("/api/queue/nope", "DELETE")[0], None
        assert code == 200

    def test_queue_accepts_a_full_path_not_just_an_id(self, seeded):
        c, root, folder = seeded
        code, entry = c.post("/api/queue", {"draft": str(folder),
                                            "platforms": ["telegraph"], "at": ""})
        assert code == 200 and entry["draft"].endswith("article.md")


class TestImages:
    def test_serves_a_draft_image(self, seeded):
        c, _, folder = seeded
        (folder / "images").mkdir(exist_ok=True)
        (folder / "images" / "hero.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        code, ctype, raw = c.get("/images/2026-09-04-a-draft/hero.jpg")
        assert code == 200 and raw == b"\xff\xd8\xff\xd9"

    def test_missing_image_is_404(self, seeded):
        c, _, _ = seeded
        assert c.get("/images/2026-09-04-a-draft/nope.jpg")[0] == 404


class TestLauncher:
    """bin/autowebpost must find an interpreter without assuming `python` exists."""

    def test_launcher_is_executable(self):
        import os
        from pathlib import Path
        script = Path(__file__).resolve().parent.parent / "bin" / "autowebpost"
        assert script.exists()
        assert os.access(script, os.X_OK)

    def test_launcher_runs_the_cli(self):
        import subprocess
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run(["bash", "bin/autowebpost", "--version"],
                           cwd=root, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip()

    def test_launcher_reaches_a_subcommand(self):
        import subprocess
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run(["bash", "bin/autowebpost", "sites", "--api-only"],
                           cwd=root, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        assert "telegraph" in r.stdout

    def test_launcher_prefers_the_venv_interpreter(self):
        from pathlib import Path
        script = (Path(__file__).resolve().parent.parent / "bin" / "autowebpost")
        body = script.read_text()
        assert ".venv/bin/python3" in body          # venv tried before system
        assert body.index(".venv/bin/python3") < body.index("command -v")

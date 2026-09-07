"""Local review dashboard - `python -m autowebpost.cli serve`.

A dependency-free web UI (stdlib http.server only, so nothing new enters
requirements.txt) over output/drafts and the publish queue. It exists to make
the human-review gate a real workflow:

    generate  ->  open the dashboard  ->  read it, tick the checklist  ->  approve
              ->  queue / publish

Safety rules, enforced server-side and not just in the UI:
  * live publishing is disabled unless the server was started with --allow-live
  * a draft must be explicitly approved before it can be published at all
  * the default host is 127.0.0.1, so it is not exposed to your network

This is a local tool for one operator. Do not put it on the public internet.
"""
from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .config import OUTPUT_DIR, load_config
from .content.engine import make_provider
from .models import ArticleDraft
from .platforms import PUBLISHERS, get_many
from .platforms.htmlutil import markdown_to_html
from .profiles import load_persona
from .review import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    draft_summary,
    is_publishable,
    iter_draft_folders,
    load_draft_folder,
    load_review,
    save_review,
    set_decision,
    set_notes,
    toggle_checklist,
)
from .scheduler import add as queue_add, entries as queue_entries, remove as queue_remove

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Auto-AI-WebPost — Review</title>
<style>
  :root{
    --bg:#0f1115; --panel:#161a21; --panel-2:#1c212b; --line:#272d38;
    --text:#e6e9ef; --muted:#98a1b3; --accent:#5b9cff;
    --ok:#3ecf8e; --warn:#f5a524; --bad:#f2555a;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  header{display:flex;align-items:center;gap:16px;padding:14px 20px;
         background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
  header h1{font-size:15px;margin:0;font-weight:600;letter-spacing:.2px}
  header .sub{color:var(--muted);font-size:12px}
  .stats{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .pill{background:var(--panel-2);border:1px solid var(--line);border-radius:999px;
        padding:4px 10px;font-size:12px;color:var(--muted)}
  .pill b{color:var(--text)}
  .pill.live{color:var(--bad);border-color:#4b2a2f}
  .pill.safe{color:var(--ok);border-color:#24493a}
  main{display:grid;grid-template-columns:360px 1fr;gap:0;height:calc(100vh - 57px)}
  #list{border-right:1px solid var(--line);overflow-y:auto;background:var(--panel)}
  .item{padding:12px 16px;border-bottom:1px solid var(--line);cursor:pointer}
  .item:hover{background:var(--panel-2)}
  .item.active{background:var(--panel-2);box-shadow:inset 3px 0 0 var(--accent)}
  .item .t{font-weight:600;margin-bottom:4px;display:flex;gap:8px;align-items:flex-start}
  .item .m{color:var(--muted);font-size:12px;display:flex;gap:10px;flex-wrap:wrap}
  .tag{font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--line);
       background:var(--panel);color:var(--muted);white-space:nowrap}
  .tag.approved{color:var(--ok);border-color:#24493a}
  .tag.rejected{color:var(--bad);border-color:#4b2a2f}
  .tag.pending{color:var(--warn);border-color:#4a3a1c}
  .tag.bad{color:var(--bad);border-color:#4b2a2f}
  #detail{overflow-y:auto;padding:24px 28px}
  .empty{color:var(--muted);padding:40px;text-align:center}
  h2.title{margin:0 0 6px;font-size:22px;line-height:1.25}
  .meta{color:var(--muted);font-size:12px;margin-bottom:16px}
  .bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:18px}
  button{background:var(--panel-2);color:var(--text);border:1px solid var(--line);
         border-radius:8px;padding:7px 13px;font-size:13px;cursor:pointer}
  button:hover{border-color:#3a4252}
  button.primary{background:var(--accent);border-color:var(--accent);color:#08111f;font-weight:600}
  button.good{background:#16382a;border-color:#24493a;color:var(--ok)}
  button.danger{background:#3a1d20;border-color:#4b2a2f;color:var(--bad)}
  button:disabled{opacity:.45;cursor:not-allowed}
  .tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:16px}
  .tab{padding:8px 14px;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent}
  .tab.active{color:var(--text);border-bottom-color:var(--accent)}
  .panel{display:none}
  .panel.active{display:block}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:14px}
  .card h3{margin:0 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted)}
  .row{display:flex;gap:12px;padding:7px 0;border-bottom:1px solid var(--line)}
  .row:last-child{border-bottom:0}
  .row .k{width:150px;color:var(--muted);flex-shrink:0;font-size:12px}
  .row .v{flex:1;word-break:break-word}
  .check{display:flex;gap:10px;align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--line)}
  .check:last-child{border-bottom:0}
  .check input{margin-top:3px;width:15px;height:15px;accent-color:var(--accent)}
  .check .txt{flex:1}
  .check.done .txt{color:var(--muted)}
  .note{font-size:11px;margin-top:2px}
  .note.auto{color:var(--ok)}
  .note.human{color:var(--warn)}
  .note.gap{color:var(--bad)}
  pre{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;
      padding:14px;overflow:auto;font-size:12px;line-height:1.5}
  .article{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:26px 30px}
  .article h2,.article h3{line-height:1.3;margin:1.4em 0 .5em}
  .article h2:first-child,.article h3:first-child{margin-top:0}
  .article p{margin:0 0 1em}
  .article table{border-collapse:collapse;width:100%;margin:1em 0;font-size:13px}
  .article th,.article td{border:1px solid var(--line);padding:7px 10px;text-align:left}
  .article th{background:var(--panel-2)}
  .article blockquote{margin:1em 0;padding:8px 14px;border-left:3px solid var(--accent);color:var(--muted)}
  .article hr{border:0;border-top:1px solid var(--line);margin:1.6em 0}
  .article code{background:var(--panel-2);padding:1px 5px;border-radius:4px;font-size:12px}
  .article pre{background:var(--panel-2);padding:12px;overflow:auto}
  .article pre code{background:none;padding:0}
  .article img{max-width:100%;border-radius:8px}
  .markers{margin-top:10px}
  .marker{background:#2a1f14;border:1px solid #4a3a1c;border-radius:8px;
          padding:9px 12px;margin-top:7px;font-size:12px;color:#f3d5a3}
  textarea{width:100%;min-height:70px;background:var(--panel-2);color:var(--text);
           border:1px solid var(--line);border-radius:8px;padding:10px;font:inherit}
  select,input[type=text]{background:var(--panel-2);color:var(--text);border:1px solid var(--line);
                          border-radius:8px;padding:7px 10px;font:inherit}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  .result{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;
          padding:10px 12px;margin-top:8px;font-size:12px;white-space:pre-wrap;word-break:break-word}
  .result.ok{border-color:#24493a}
  .result.bad{border-color:#4b2a2f}
  .plats{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
  .plat{display:flex;align-items:center;gap:5px;background:var(--panel-2);
        border:1px solid var(--line);border-radius:8px;padding:5px 9px;font-size:12px}
  .plat input{accent-color:var(--accent)}
  .dim{color:var(--muted)}
</style>
</head>
<body>
<header>
  <h1>Auto-AI-WebPost <span class="sub">· review gate</span></h1>
  <div class="stats" id="stats"></div>
</header>
<main>
  <div id="list"></div>
  <div id="detail"><div class="empty">Select a draft</div></div>
</main>

<script>
const state = { drafts: [], current: null, tab: "preview", status: null };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || r.statusText || "request failed");
  return body;
}

function pill(cls, text, title) {
  return `<span class="tag ${cls}" ${title ? `title="${esc(title)}"` : ""}>${esc(text)}</span>`;
}

function renderStats() {
  const d = state.drafts, s = state.status || {};
  const pending = d.filter(x => x.status === "pending").length;
  const approved = d.filter(x => x.status === "approved").length;
  const flagged = d.filter(x => x.marker_count > 0).length;
  const queued = (s.queue_count ?? 0);
  let html = "";
  html += `<span class="pill">drafts <b>${d.length}</b></span>`;
  html += `<span class="pill">pending <b>${pending}</b></span>`;
  html += `<span class="pill">approved <b>${approved}</b></span>`;
  html += `<span class="pill">unresolved markers <b>${flagged}</b></span>`;
  html += `<span class="pill">queued <b>${queued}</b></span>`;
  html += s.allow_live
    ? `<span class="pill live" title="server started with --allow-live">LIVE PUBLISH ON</span>`
    : `<span class="pill safe" title="publishing is dry-run only">dry-run only</span>`;
  $("#stats").innerHTML = html;
}

function renderList() {
  const el = $("#list");
  if (!state.drafts.length) {
    el.innerHTML = `<div class="empty">No drafts yet.<br><br>
      <code>autowebpost generate --topic "..."</code></div>`;
    return;
  }
  el.innerHTML = state.drafts.map(d => {
    const p = d.progress || {};
    const pct = p.total ? Math.round(p.done / p.total * 100) : 0;
    return `<div class="item ${state.current === d.id ? "active" : ""}" data-id="${esc(d.id)}">
      <div class="t"><span>${esc(d.title)}</span></div>
      <div class="m">
        ${pill(d.status, d.status)}
        <span>${p.done}/${p.total} E-E-A-T</span>
        <span>${d.words}w</span>
        ${d.marker_count ? pill("bad", d.marker_count + " EDIT-ME") : ""}
      </div>
      <div class="m" style="margin-top:6px">
        <span>${esc(d.id.split("-").slice(0,3).join("-"))}</span>
        <span>${esc(d.generator || "")}</span>
      </div>
    </div>`;
  }).join("");
  el.querySelectorAll(".item").forEach(n =>
    n.addEventListener("click", () => open(n.dataset.id)));
}

async function open(id) {
  state.current = id;
  state.tab = "preview";
  renderList();
  $("#detail").innerHTML = `<div class="empty">Loading…</div>`;
  const d = await api("/api/drafts/" + encodeURIComponent(id));
  renderDetail(d);
}

function renderDetail(d) {
  const p = d.progress || {};
  const pub = d.publishable;
  const h = [];
  h.push(`<h2 class="title">${esc(d.title)}</h2>`);
  h.push(`<div class="meta">${esc(d.folder)} · ${esc(d.generator||"")} ·
          ${d.words} words · ${d.faq_count} FAQ · ${d.reference_count} refs ·
          ${d.image_count} images</div>`);

  h.push(`<div class="bar">
    <button class="good" data-act="approve" ${d.status==="approved"?"disabled":""}>Approve</button>
    <button class="danger" data-act="reject" ${d.status==="rejected"?"disabled":""}>Reject</button>
    <button data-act="reset" ${d.status==="pending"?"disabled":""}>Reset</button>
    ${pub ? pill("approved","approved — publishable") : pill("pending","not approved")}
    ${d.decided_at ? `<span class="dim">${esc(d.decided_at)}</span>` : ""}
  </div>`);

  h.push(`<div class="tabs">
    <div class="tab ${state.tab==="preview"?"active":""}" data-tab="preview">Preview</div>
    <div class="tab ${state.tab==="seo"?"active":""}" data-tab="seo">SEO &amp; schema</div>
    <div class="tab ${state.tab==="checklist"?"active":""}" data-tab="checklist">
      Checklist ${p.done}/${p.total}</div>
    <div class="tab ${state.tab==="publish"?"active":""}" data-tab="publish">Publish</div>
  </div>`);

  if (state.tab === "preview") {
    h.push(`<div class="card"><h3>Meta</h3>
      <div class="row"><div class="k">primary keyword</div><div class="v">${esc(d.primary_keyword||"—")}</div></div>
      <div class="row"><div class="k">meta description</div><div class="v">${esc(d.meta_description||"—")}
        <span class="dim">(${esc(String((d.meta_description||"").length))} chars)</span></div></div>
      <div class="row"><div class="k">tags</div><div class="v">${esc((d.tags||[]).join(", ")||"—")}</div></div>
      <div class="row"><div class="k">canonical URL</div><div class="v">${d.canonical_url?esc(d.canonical_url):'<span class="dim">not set</span>'}</div></div>
    </div>`);
    if (d.marker_count) {
      h.push(`<div class="card"><h3>Unresolved EDIT-ME markers (${d.marker_count})</h3>
        <div class="dim">These are instructions to you, not content. Replace every one before publishing.</div>
        <div class="markers">${d.markers.map(m=>`<div class="marker">${esc(m)}</div>`).join("")}</div>
      </div>`);
    }
    h.push(`<div class="card"><h3>Article preview</h3></div>`);
    h.push(`<div class="article">${d.html || '<span class="dim">empty</span>'}</div>`);
  }

  if (state.tab === "seo") {
    h.push(`<div class="card"><h3>Structured data (seo.jsonld.txt)</h3>
      <pre>${esc(d.jsonld || "(none)")}</pre></div>`);
    h.push(`<div class="card"><h3>Front matter</h3><pre>${esc(d.front_matter||"")}</pre></div>`);
  }

  if (state.tab === "checklist") {
    h.push(`<div class="card"><h3>E-E-A-T gate</h3>`);
    (d.checklist||[]).forEach((c,i) => {
      h.push(`<label class="check ${c.done?"done":""}">
        <input type="checkbox" data-check="${esc(c.item)}" ${c.manual?"checked":""}>
        <div class="txt">${esc(c.item)}
          ${c.auto === true ? `<div class="note auto">verified automatically</div>`
            : c.auto === false ? `<div class="note gap">not satisfied yet</div>`
            : `<div class="note human">you must confirm this yourself</div>`}
        </div></label>`);
    });
    h.push(`</div>`);
    h.push(`<div class="card"><h3>Reviewer notes</h3>
      <textarea id="notes" placeholder="Why this is (or isn't) ready…">${esc(d.notes||"")}</textarea>
      <div style="margin-top:8px"><button data-act="notes">Save notes</button></div></div>`);
  }

  if (state.tab === "publish") {
    const plats = (state.status && state.status.platforms) || [];
    h.push(`<div class="card"><h3>Platforms</h3>
      <div class="plats">${plats.map(sl => `<label class="plat">
        <input type="checkbox" class="plat-cb" value="${esc(sl)}">${esc(sl)}</label>`).join("")}</div>
      <div class="dim">Draft where the platform supports it; canonical URL is sent when set.</div>
    </div>`);
    h.push(`<div class="card"><h3>Queue for later</h3>
      <div class="grid2">
        <div><div class="dim">publish at (UTC, YYYY-MM-DD HH:MM)</div>
          <input type="text" id="q-at" placeholder="blank = now"></div>
        <div><div class="dim">stagger minutes between platforms</div>
          <input type="text" id="q-delay" value="30"></div>
      </div>
      <div style="margin-top:10px"><button data-act="queue">Add to queue</button></div>
    </div>`);
    h.push(`<div class="card"><h3>Publish now</h3>
      <div class="dim" id="pub-help">${state.status && state.status.allow_live
        ? "This server was started with --allow-live, so a live publish will really post."
        : "Dry-run only on this server (start with --allow-live to enable real publishing)."}</div>
      <div style="margin-top:10px">
        <button class="primary" data-act="publish">Dry run</button>
        ${(state.status && state.status.allow_live)
          ? `<button class="danger" data-act="publish-live" ${pub?"":"disabled"}>Publish live</button>` : ""}
      </div>
      ${pub ? "" : `<div class="note human" style="margin-top:8px">Approve this draft first.</div>`}
      <div id="pub-results"></div>
    </div>`);
  }

  $("#detail").innerHTML = h.join("");
  bind(d);
}

function bind(d) {
  $("#detail").querySelectorAll(".tab").forEach(t =>
    t.addEventListener("click", () => { state.tab = t.dataset.tab; renderDetail(d); }));

  const act = async (a, fn) => {
    const btns = $("#detail").querySelectorAll(`[data-act="${a}"]`);
    try { await fn(); } catch (e) { alert(String(e.message || e)); }
  };

  const setStatus = (s) => act(s, async () => {
    const r = await api(`/api/drafts/${encodeURIComponent(d.id)}/decision`,
      {method:"POST", headers:{"Content-Type":"application/json"},
       body: JSON.stringify({status: s})});
    await refresh(r);
  });
  const b = (n) => $("#detail").querySelector(`[data-act="${n}"]`);
  if (b("approve")) b("approve").addEventListener("click", () => setStatus("approved"));
  if (b("reject"))  b("reject").addEventListener("click", () => setStatus("rejected"));
  if (b("reset"))   b("reset").addEventListener("click", () => setStatus("pending"));
  if (b("notes"))   b("notes").addEventListener("click", () => act("notes", async () => {
    await api(`/api/drafts/${encodeURIComponent(d.id)}/notes`,
      {method:"POST", headers:{"Content-Type":"application/json"},
       body: JSON.stringify({notes: $("#notes").value})});
  }));

  $("#detail").querySelectorAll("[data-check]").forEach(cb =>
    cb.addEventListener("change", async () => {
      try {
        await api(`/api/drafts/${encodeURIComponent(d.id)}/checklist`,
          {method:"POST", headers:{"Content-Type":"application/json"},
           body: JSON.stringify({item: cb.dataset.check, done: cb.checked})});
        const fresh = await api("/api/drafts/" + encodeURIComponent(d.id));
        Object.assign(d, fresh);
        renderList();
      } catch (e) { alert(String(e.message || e)); }
    }));

  if (b("queue")) b("queue").addEventListener("click", () => act("queue", async () => {
    const platforms = [...document.querySelectorAll(".plat-cb:checked")].map(x => x.value);
    if (!platforms.length) return alert("Pick at least one platform.");
    await api("/api/queue", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({draft: d.folder, platforms,
        at: $("#q-at").value, delay: parseInt($("#q-delay").value || "0", 10)})});
    await loadStatus(); renderStats();
    alert("Queued.");
  }));

  const publish = (live) => act(live ? "publish-live" : "publish", async () => {
    const platforms = [...document.querySelectorAll(".plat-cb:checked")].map(x => x.value);
    if (!platforms.length) return alert("Pick at least one platform.");
    if (live && !confirm("Publish LIVE now to " + platforms.join(", ") + "?")) return;
    const r = await api("/api/publish", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({draft: d.folder, platforms, live})});
    $("#pub-results").innerHTML = (r.results || []).map(x =>
      `<div class="result ${x.ok?"ok":"bad"}"><b>${esc(x.platform)}</b> — ${esc(x.detail||x.url||"")}</div>`
    ).join("") || '<div class="result">no results</div>';
    await loadStatus(); renderStats();
  });
  if (b("publish")) b("publish").addEventListener("click", () => publish(false));
  if (b("publish-live")) b("publish-live").addEventListener("click", () => publish(true));
}

async function refresh(updated) {
  await loadDrafts();
  if (updated && updated.summary) {
    const i = state.drafts.findIndex(x => x.id === updated.summary.id);
    if (i >= 0) state.drafts[i] = updated.summary;
  }
  renderStats(); renderList();
  const d = await api("/api/drafts/" + encodeURIComponent(state.current));
  renderDetail(d);
}

async function loadDrafts() { state.drafts = await api("/api/drafts"); }
async function loadStatus() { state.status = await api("/api/status"); }

(async function init() {
  await loadStatus();
  await loadDrafts();
  renderStats();
  renderList();
  if (state.drafts.length) open(state.drafts[0].id);
})();
</script>
</body>
</html>
"""


class Dashboard:
    """Holds server configuration and resolves drafts safely."""

    def __init__(self, drafts_dir: Optional[Path] = None, allow_live: bool = False):
        self.drafts_dir = Path(drafts_dir) if drafts_dir else (OUTPUT_DIR / "drafts")
        self.allow_live = allow_live

    def folder_for(self, draft_id: str) -> Path:
        """Resolve a draft id to its folder, refusing anything outside drafts_dir.

        draft_id comes straight from the URL, so this is the path-traversal guard.
        """
        if not draft_id or draft_id in (".", "..") or "/" in draft_id or "\\" in draft_id:
            raise LookupError("invalid draft id")
        base = self.drafts_dir.resolve()
        folder = (base / draft_id).resolve()
        if folder.parent != base or not folder.is_dir():
            raise LookupError("no such draft")
        return folder

    def summaries(self):
        persona = load_persona()
        out = []
        for folder in iter_draft_folders(self.drafts_dir):
            draft = load_draft_folder(folder)
            if draft is None:
                continue
            out.append(draft_summary(folder, draft, persona))
        return out


def _jsonld_for(folder: Path) -> str:
    p = Path(folder) / "seo.jsonld.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _front_matter(folder: Path) -> str:
    text = (Path(folder) / "article.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    return m.group(1) if m else ""


def _publish(dashboard: Dashboard, draft_folder: Path, platforms, live: bool):
    """Publish one draft. Approval is required; live requires --allow-live."""
    draft = ArticleDraft.load(draft_folder / "article.md")
    persona = load_persona()
    review = load_review(draft_folder)

    if not is_publishable(draft, persona, review):
        raise PermissionError("draft is not approved - approve it in the dashboard first")
    if live and not dashboard.allow_live:
        raise PermissionError("live publishing is disabled (start the server with --allow-live)")

    publishers = get_many(platforms)
    results = []
    for pub in publishers:
        r = pub.publish(draft, persona, live=live)
        results.append({"platform": pub.slug, "ok": r.ok, "url": r.url,
                        "detail": r.detail, "dry_run": r.dry_run})
    return results


class Handler(BaseHTTPRequestHandler):
    server_version = "AutoAIWebPost/0.1"
    dashboard: Dashboard = None  # set by make_handler

    # ---- plumbing -----------------------------------------------------
    def log_message(self, fmt, *args):  # keep the console readable
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def _path(self) -> str:
        return urlparse(self.path).path

    # ---- routes -------------------------------------------------------
    def do_GET(self):
        p = self._path()
        try:
            if p == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if p == "/api/status":
                return self._send(200, self._status())
            if p == "/api/drafts":
                return self._send(200, self.dashboard.summaries())
            if p.startswith("/api/drafts/"):
                did = p[len("/api/drafts/"):].strip("/")
                return self._send(200, self._draft_detail(did))
            if p == "/api/queue":
                return self._send(200, queue_entries())
            if p.startswith("/images/"):
                return self._serve_image(p[len("/images/"):])
        except LookupError as e:
            return self._send(404, {"error": str(e)})
        except Exception as e:  # noqa: BLE001 - never leak a traceback to the UI
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = self._path()
        body = self._body()
        try:
            if p.startswith("/api/drafts/") and p.endswith("/decision"):
                did = p[len("/api/drafts/"):-len("/decision")].strip("/")
                folder = self.dashboard.folder_for(did)
                state = set_decision(folder, body.get("status", ""))
                return self._send(200, {"summary": self._summary(folder),
                                        "status": state.status})
            if p.startswith("/api/drafts/") and p.endswith("/checklist"):
                did = p[len("/api/drafts/"):-len("/checklist")].strip("/")
                folder = self.dashboard.folder_for(did)
                checklist = toggle_checklist(folder, str(body.get("item", "")),
                                             bool(body.get("done")))
                return self._send(200, {"checklist": checklist})
            if p.startswith("/api/drafts/") and p.endswith("/notes"):
                did = p[len("/api/drafts/"):-len("/notes")].strip("/")
                folder = self.dashboard.folder_for(did)
                state = set_notes(folder, str(body.get("notes", "")))
                return self._send(200, {"notes": state.notes})
            if p == "/api/queue":
                folder = self.dashboard.folder_for(
                    Path(str(body.get("draft", ""))).name)
                entry = queue_add(
                    str(folder / "article.md"),
                    [str(x) for x in (body.get("platforms") or [])],
                    str(body.get("at") or ""),
                    delay_minutes=int(body.get("delay") or 0),
                )
                return self._send(200, entry)
            if p == "/api/publish":
                folder = self.dashboard.folder_for(
                    Path(str(body.get("draft", ""))).name)
                results = _publish(self.dashboard, folder,
                                   [str(x) for x in (body.get("platforms") or [])],
                                   live=bool(body.get("live")))
                return self._send(200, {"results": results})
        except KeyError as e:
            # Unknown platform slug. KeyError subclasses LookupError, so this
            # must come first or it would be reported as a missing draft (404).
            return self._send(400, {"error": str(e).strip("'\"")})
        except LookupError as e:
            return self._send(404, {"error": str(e)})
        except PermissionError as e:
            return self._send(403, {"error": str(e)})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        return self._send(404, {"error": "not found"})

    def do_DELETE(self):
        p = self._path()
        try:
            if p.startswith("/api/queue/"):
                eid = p[len("/api/queue/"):].strip("/")
                return self._send(200, {"removed": bool(queue_remove(eid))})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        return self._send(404, {"error": "not found"})

    # ---- helpers ------------------------------------------------------
    def _status(self):
        cfg = load_config()
        try:
            provider = make_provider(cfg.get("content", {})).name
        except Exception:
            provider = "unavailable"
        persona = load_persona()
        return {
            "persona": persona.name,
            "provider": provider,
            "allow_live": self.dashboard.allow_live,
            "drafts_dir": str(self.dashboard.drafts_dir),
            "platforms": sorted(PUBLISHERS),
            "queue_count": len(queue_entries()),
        }

    def _summary(self, folder: Path):
        draft = load_draft_folder(folder)
        return draft_summary(folder, draft, load_persona()) if draft else None

    def _draft_detail(self, draft_id: str):
        folder = self.dashboard.folder_for(draft_id)
        draft = load_draft_folder(folder)
        if draft is None:
            raise LookupError("no article.md in that folder")
        summary = draft_summary(folder, draft, load_persona())
        summary.update({
            "html": markdown_to_html(draft.body_markdown),
            "jsonld": _jsonld_for(folder),
            "front_matter": _front_matter(folder),
        })
        return summary

    def _serve_image(self, rel: str):
        """Serve a generated draft image (referenced by the article preview)."""
        folder = self.dashboard.folder_for(rel.split("/")[0])
        img = folder / "images" / Path(rel).name
        if not img.exists():
            raise LookupError("no such image")
        ctype = mimetypes.guess_type(img.name)[0] or "application/octet-stream"
        self._send(200, img.read_bytes(), ctype)


def make_handler(dashboard: Dashboard):
    return type("DashboardHandler", (Handler,), {"dashboard": dashboard})


def create_server(host: str = "127.0.0.1", port: int = 8765, allow_live: bool = False,
                  drafts_dir: Optional[Path] = None) -> ThreadingHTTPServer:
    dashboard = Dashboard(drafts_dir=drafts_dir, allow_live=allow_live)
    return ThreadingHTTPServer((host, port), make_handler(dashboard))


def serve(host: str = "127.0.0.1", port: int = 8765, allow_live: bool = False,
          drafts_dir: Optional[Path] = None, open_browser: bool = True) -> None:
    """Run the dashboard until interrupted."""
    import webbrowser

    httpd = create_server(host, port, allow_live, drafts_dir)
    url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}/"
    print(f"\n  Auto-AI-WebPost review dashboard")
    print(f"  {url}")
    print(f"  drafts    : {httpd.RequestHandlerClass.dashboard.drafts_dir}")
    print(f"  live post : {'ENABLED' if allow_live else 'disabled (dry-run only)'}")
    if host in ("0.0.0.0", ""):
        print("\n  NOTE: bound to all interfaces - reachable from your network.")
        print("        On your Mac, prefer the default: --host 127.0.0.1\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        # short poll interval so Ctrl-C (and shutdown) returns promptly
        httpd.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        print("\n  stopped\n")
    finally:
        httpd.server_close()

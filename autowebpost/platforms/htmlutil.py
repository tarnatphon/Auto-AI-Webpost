"""Minimal markdown -> HTML and -> Telegraph node-tree converters.

Covers what our generated articles contain: headings, paragraphs, bold/italic/
code, links, images, lists, tables (HTML), blockquotes, hr.
"""
from __future__ import annotations

import html
import re
from typing import Dict, List


def _inline(md: str) -> str:
    md = html.escape(md, quote=False)
    md = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)", r'<img src="\2" alt="\1"/>', md)
    md = re.sub(r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)", r'<a href="\2">\1</a>', md)
    md = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", md)
    md = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", md)
    md = re.sub(r"`([^`]+)`", r"<code>\1</code>", md)
    return md


def markdown_to_html(md: str) -> str:
    out: List[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s or s.startswith("<!--"):
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            header, body_rows = rows[0], rows[2:]
            t = "<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in header) + "</tr></thead><tbody>"
            for r in body_rows:
                t += "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
            out.append(t + "</tbody></table>")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            lvl = min(len(m.group(1)) + 1, 6)  # h1 -> h2 semantics
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if s.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            continue
        if s in ("---", "***", "___"):
            out.append("<hr/>")
            i += 1
            continue
        if s.startswith("> "):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip("> "))
                i += 1
            out.append("<blockquote>" + _inline(" ".join(quote)) + "</blockquote>")
            continue
        if re.match(r"^[-*]\s+", s) or re.match(r"^\d+\.\s+", s):
            ordered = bool(re.match(r"^\d+\.", s))
            items = []
            while i < len(lines) and (re.match(r"^[-*]\s+", lines[i].strip()) or re.match(r"^\d+\.\s+", lines[i].strip())):
                items.append("<li>" + _inline(re.sub(r"^([-*]|\d+\.)\s+", "", lines[i].strip())) + "</li>")
                i += 1
            out.append(("" % ()) + (f"<ol>{''.join(items)}</ol>" if ordered else f"<ul>{''.join(items)}</ul>"))
            continue
        para = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|[-*]\s|\d+\.\s|>|\||```|---)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append("<p>" + _inline(" ".join(para)) + "</p>")
    return "\n".join(out)


def html_to_telegraph_nodes(html_str: str) -> List[Dict]:
    """Very small converter: p/h3/h4/b/strong/i/em/a/img/ul/ol/li/blockquote/pre/hr.
    Telegraph supports: a, aside, b, blockquote, br, code, em, figcaption,
    figure, h3, h4, hr, i, iframe, img, li, ol, p, pre, s, strong, u, ul, video."""
    text = re.sub(r"</?(thead|tbody|table|tr|th|td)>", "", html_str)
    text = text.replace("<th>", "<b>").replace("</th>", "</b>")
    text = text.replace("<td>", "").replace("</td>", " ")
    text = re.sub(r"<h2>", "<h3>", text).replace("</h2>", "</h3>")
    text = re.sub(r"<h5>|<h6>", "<h4>", text).replace("</h5>", "</h4>").replace("</h6>", "</h4>")
    nodes: List[Dict] = []
    for m in re.finditer(r"<(p|h3|h4|blockquote|pre|ul|ol|img|hr)\b[^>]*>(.*?)</\1>|<(img|hr)\b[^>]*/?>", text, re.S):
        tag = m.group(1) or m.group(3)
        inner = (m.group(2) or "").strip()
        if tag == "img":
            src = re.search(r'src="([^"]+)"', m.group(0))
            alt = re.search(r'alt="([^"]*)"', m.group(0))
            if src:
                nodes.append({"tag": "img", "attrs": {"src": src.group(1), "alt": alt.group(1) if alt else ""}})
        elif tag == "hr":
            nodes.append({"tag": "hr"})
        elif tag in ("ul", "ol"):
            items = re.findall(r"<li>(.*?)</li>", inner, re.S)
            nodes.append({"tag": tag, "children": [{"tag": "li", "children": [_t(x)]} for x in items]})
        elif tag == "pre":
            nodes.append({"tag": "pre", "children": [_t(re.sub(r"<[^>]+>", "", inner))]})
        else:
            nodes.append({"tag": tag, "children": [_t(inner)]})
    # drop images that point at local files (telegraph needs public URLs)
    return [n for n in nodes if not (n.get("tag") == "img" and n["attrs"]["src"].startswith(("output/", "./", "/")))]


def _t(fragment: str) -> Dict:
    """Parse tiny inline html into telegraph children (text + a + b + em + code)."""
    children: List = []
    pos = 0
    for m in re.finditer(r"<(a|b|strong|em|i|code)\b[^>]*>(.*?)</\1>", fragment, re.S):
        if m.start() > pos:
            children.append(fragment[pos:m.start()])
        inner = m.group(2)
        if m.group(1) == "a":
            href = re.search(r'href="([^"]+)"', m.group(0))
            children.append({"tag": "a", "attrs": {"href": href.group(1) if href else "#"}, "children": [inner]})
        elif m.group(1) in ("b", "strong"):
            children.append({"tag": "strong", "children": [inner]})
        elif m.group(1) in ("i", "em"):
            children.append({"tag": "em", "children": [inner]})
        else:
            children.append({"tag": "code", "children": [inner]})
        pos = m.end()
    if pos < len(fragment):
        children.append(fragment[pos:])
    return children or [""]

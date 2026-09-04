"""Markdown -> HTML -> Telegraph node conversion (used by every HTML platform)."""
from __future__ import annotations

from autowebpost.platforms.htmlutil import html_to_telegraph_nodes, markdown_to_html


class TestMarkdownToHtml:
    def test_headings_shift_one_level(self):
        html = markdown_to_html("# Title\n\n## Section")
        assert "<h2>Title</h2>" in html and "<h3>Section</h3>" in html

    def test_paragraphs(self):
        assert "<p>Hello world</p>" in markdown_to_html("Hello world")

    def test_bold_and_italic(self):
        html = markdown_to_html("**bold** and *italic*")
        assert "<strong>bold</strong>" in html and "<em>italic</em>" in html

    def test_inline_code(self):
        assert "<code>x = 1</code>" in markdown_to_html("`x = 1`")

    def test_links(self):
        assert '<a href="https://example.com">text</a>' in markdown_to_html(
            "[text](https://example.com)")

    def test_images(self):
        html = markdown_to_html("![alt text](images/hero.jpg)")
        assert '<img src="images/hero.jpg" alt="alt text"/>' in html

    def test_unordered_and_ordered_lists(self):
        html = markdown_to_html("- a\n- b")
        assert "<ul><li>a</li><li>b</li></ul>" in html
        html = markdown_to_html("1. a\n2. b")
        assert "<ol><li>a</li><li>b</li></ol>" in html

    def test_tables(self):
        html = markdown_to_html("| A | B |\n|---|---|\n| 1 | 2 |")
        assert "<table>" in html and "<th>A</th>" in html and "<td>1</td>" in html

    def test_horizontal_rule(self):
        assert "<hr/>" in markdown_to_html("---")

    def test_blockquote(self):
        assert "<blockquote>quoted</blockquote>" in markdown_to_html("> quoted")

    def test_fenced_code_block(self):
        html = markdown_to_html("```\nprint(1)\n```")
        assert "<pre><code>print(1)</code></pre>" in html

    def test_html_is_escaped(self):
        """Article text must not be able to inject markup into a published page."""
        html = markdown_to_html("<script>alert(1)</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_html_comments_are_dropped(self):
        """EDIT-ME markers must never ship to a live page."""
        assert "EDIT-ME" not in markdown_to_html("<!-- EDIT-ME: fill this in -->\n\nReal text")

    def test_consecutive_lines_join_one_paragraph(self):
        html = markdown_to_html("line one\nline two")
        assert html.count("<p>") == 1 and "line one line two" in html


class TestTelegraphNodes:
    def test_paragraphs_become_p_nodes(self):
        # Telegraph children are a flat list of nodes (strings or element
        # objects) - a nested list is rejected by the API.
        nodes = html_to_telegraph_nodes(markdown_to_html("Hello"))
        assert nodes == [{"tag": "p", "children": ["Hello"]}]

    def test_headings_become_h3(self):
        nodes = html_to_telegraph_nodes(markdown_to_html("## Section"))
        assert nodes[0]["tag"] == "h3"

    def test_deep_headings_are_clamped_to_h4(self):
        nodes = html_to_telegraph_nodes(markdown_to_html("###### Deep"))
        assert nodes[0]["tag"] == "h4"

    def test_lists_keep_the_li_children(self):
        nodes = html_to_telegraph_nodes(markdown_to_html("- a\n- b"))
        assert nodes[0]["tag"] == "ul"
        assert nodes[0]["children"] == [{"tag": "li", "children": ["a"]},
                                        {"tag": "li", "children": ["b"]}]

    def test_only_telegraph_supported_tags_survive(self):
        """Telegraph rejects anything outside its tag whitelist."""
        allowed = {"p", "h3", "h4", "blockquote", "pre", "ul", "ol", "li", "img", "hr",
                   "a", "b", "strong", "i", "em", "code", "br", "figure", "figcaption",
                   "aside", "iframe", "s", "u", "video"}
        nodes = html_to_telegraph_nodes(markdown_to_html(
            "# T\n\ntext\n\n- a\n\n> quote\n\n```\ncode\n```\n\n---\n"))
        tags = set()

        def walk(ns):
            for n in ns:
                if isinstance(n, dict):
                    if "tag" in n:
                        tags.add(n["tag"])
                    walk(n.get("children") or [])
        walk(nodes)
        assert tags <= allowed, tags - allowed

    def test_remote_images_are_kept(self):
        nodes = html_to_telegraph_nodes('<img src="https://cdn.example.com/a.jpg" alt="a"/>')
        assert nodes == [{"tag": "img", "attrs": {"src": "https://cdn.example.com/a.jpg",
                                                  "alt": "a"}}]

    def test_local_images_are_dropped(self):
        """Local files can't be rendered by telegra.ph - dropping beats a broken img."""
        for src in ("images/hero.jpg", "./images/hero.jpg", "/tmp/hero.jpg",
                    "output/drafts/x/images/hero.jpg"):
            nodes = html_to_telegraph_nodes(f'<img src="{src}" alt="a"/>')
            assert nodes == [], src

    def test_links_become_a_nodes(self):
        nodes = html_to_telegraph_nodes('<p><a href="https://x.com">go</a></p>')
        assert {"tag": "a", "attrs": {"href": "https://x.com"}, "children": ["go"]} in nodes[0]["children"]

    def test_empty_input_yields_no_nodes(self):
        assert html_to_telegraph_nodes("") == []

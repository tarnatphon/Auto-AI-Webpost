import unittest
from autowebpost.platforms.htmlutil import markdown_to_html, html_to_telegraph_nodes


class TestHtmlUtil(unittest.TestCase):
    def test_telegraph_node_tree_structure(self):
        md = "# Heading 1\n\nParagraph with **bold** and *italic* and [link](https://example.com).\n\n- list item 1\n- list item 2"
        html = markdown_to_html(md)
        nodes = html_to_telegraph_nodes(html)

        self.assertIsInstance(nodes, list)
        for node in nodes:
            self.assertIsInstance(node, dict)
            self.assertIn("tag", node)
            if "children" in node:
                self.assertIsInstance(node["children"], list)
                for child in node["children"]:
                    # Child must be a string or a dict element, never a nested list
                    self.assertFalse(isinstance(child, list), f"Nested list found in {node['tag']} children: {child}")


if __name__ == "__main__":
    unittest.main()

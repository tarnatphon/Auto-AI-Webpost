"""E-E-A-T content blocks: first-hand experience and references building."""
from __future__ import annotations

from autowebpost.content.eeat import experience_block, references_section


class TestExperienceBlock:
    def test_keeps_the_edit_me_marker_on_purpose(self, persona):
        block = experience_block(persona, "AI auto posting")
        assert "My experience with ai auto posting" in block
        assert f"for over {persona.experience_years} years" in block
        assert "EDIT-ME" in block
        assert "First-hand experience" in block


class TestReferencesSection:
    def test_empty_references_render_nothing(self):
        assert references_section([]) == ""

    def test_ordered_references_render_numbered_lines(self):
        out = references_section(["https://example.com/a", "https://example.com/b"])
        assert "## References and further reading" in out
        assert "1. https://example.com/a" in out
        assert "2. https://example.com/b" in out

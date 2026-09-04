"""Keyword research (Google Autocomplete + DuckDuckGo fallback), HTTP mocked."""
from __future__ import annotations

import pytest
import requests

from autowebpost.research.keywords import expand, suggest


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("boom", response=self)

    def json(self):
        return self._payload


def route(monkeypatch, mapping):
    """Route GETs by URL substring -> FakeResponse (or raise)."""
    seen = []

    def _get(url, **kw):
        seen.append(url)
        for pattern, value in mapping.items():
            if pattern in url:
                if isinstance(value, Exception):
                    raise value
                return value if isinstance(value, FakeResponse) else FakeResponse(**value)
        return FakeResponse([])
    monkeypatch.setattr(requests, "get", _get)
    return seen


GOOGLE = "suggestqueries.google.com"
DDG = "duckduckgo.com/ac/"


class TestSuggest:
    def test_returns_google_suggestions(self, monkeypatch):
        seen = route(monkeypatch, {GOOGLE: FakeResponse(["ai content", ["a", "b", "c"]])})
        assert suggest("ai content") == ["a", "b", "c"]
        assert len(seen) == 1 and GOOGLE in seen[0]

    def test_caps_at_twelve(self, monkeypatch):
        route(monkeypatch, {GOOGLE: FakeResponse(["q", [f"s{i}" for i in range(30)]])})
        assert len(suggest("q")) == 12

    def test_falls_back_to_duckduckgo(self, monkeypatch):
        seen = route(monkeypatch, {
            GOOGLE: requests.ConnectionError("no route"),
            DDG: FakeResponse([["ddg one", 1], ["ddg two", 2]]),
        })
        assert suggest("ai") == ["ddg one", "ddg two"]
        assert len(seen) == 2

    def test_returns_empty_when_both_sources_fail(self, monkeypatch):
        """Must not raise - the CLI surfaces this as a connectivity hint."""
        route(monkeypatch, {
            GOOGLE: requests.ConnectionError("down"),
            DDG: requests.ConnectionError("down"),
        })
        assert suggest("ai") == []

    def test_http_error_triggers_the_fallback(self, monkeypatch):
        route(monkeypatch, {GOOGLE: FakeResponse({}, status=503), DDG: FakeResponse([["ok", 1]])})
        assert suggest("ai") == ["ok"]

    def test_malformed_payload_falls_back_instead_of_crashing(self, monkeypatch):
        route(monkeypatch, {GOOGLE: FakeResponse(["only-one-element"]), DDG: FakeResponse([["x", 0]])})
        assert suggest("ai") == ["x"]


class TestExpand:
    def test_collects_alphabet_and_question_variants(self, monkeypatch):
        route(monkeypatch, {GOOGLE: FakeResponse(["q", ["ai content tools", "ai content free"]])})
        data = expand("ai content")
        assert data["seed"] == "ai content"
        assert data["alphabet"] and data["questions"]

    def test_deduplicates_and_sorts(self, monkeypatch):
        route(monkeypatch, {GOOGLE: FakeResponse(["q", ["b result", "a result", "b result"]])})
        alphabet = expand("x")["alphabet"]
        assert alphabet == sorted(set(alphabet))

    def test_caps_each_section_at_twenty(self, monkeypatch):
        route(monkeypatch, {GOOGLE: FakeResponse(["q", [f"s{i}" for i in range(40)]])})
        data = expand("x")
        assert len(data["alphabet"]) <= 20 and len(data["questions"]) <= 20

    def test_excludes_the_bare_seed_keyword(self, monkeypatch):
        route(monkeypatch, {GOOGLE: FakeResponse(["q", ["ai content", "ai content tools"]])})
        assert "ai content" not in expand("ai content")["alphabet"]

    def test_survives_total_network_failure(self, monkeypatch):
        route(monkeypatch, {GOOGLE: requests.ConnectionError("down"),
                            DDG: requests.ConnectionError("down")})
        data = expand("x")
        assert data["alphabet"] == [] and data["questions"] == []

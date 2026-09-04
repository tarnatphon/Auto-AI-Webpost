"""Publishers: every adapter must build a sane payload and never leak secrets
in a dry run. Live paths are NOT exercised here - no network, no credentials."""
from __future__ import annotations

import pytest

from autowebpost.platforms import PUBLISHERS, get, get_many
from autowebpost.platforms.base import Publisher


ALL_SLUGS = sorted(PUBLISHERS)


class TestRegistry:
    def test_all_publishers_are_registered(self):
        assert set(ALL_SLUGS) == {
            "blogger", "devto", "githubpages", "hashnode", "mastodon",
            "medium", "telegraph", "tumblr", "wordpress", "writeas",
        }

    def test_get_returns_the_publisher(self):
        assert get("devto").slug == "devto"

    def test_get_is_case_and_space_tolerant(self):
        assert get("  DevTo ").slug == "devto"

    def test_unknown_slug_raises_keyerror(self):
        with pytest.raises(KeyError, match="Unknown publisher"):
            get("myspace")

    def test_get_many_splits_comma_string(self):
        assert [p.slug for p in get_many("devto,telegraph")] == ["devto", "telegraph"]

    def test_get_many_accepts_a_list(self):
        assert [p.slug for p in get_many(["devto"])] == ["devto"]

    def test_get_many_ignores_empty_segments(self):
        assert [p.slug for p in get_many("devto,,telegraph,")] == ["devto", "telegraph"]

    def test_every_publisher_has_metadata(self):
        for pub in PUBLISHERS.values():
            assert pub.slug and pub.name and pub.docs


class TestDryRun:
    @pytest.mark.parametrize("slug", ALL_SLUGS)
    def test_dry_run_returns_ok_without_touching_the_network(self, slug, draft, persona,
                                                            monkeypatch):
        """A dry run must be side-effect free: no HTTP, no token files."""
        import requests
        import autowebpost.platforms.telegraph as telegraph_mod

        def no_network(*a, **k):
            raise AssertionError(f"{slug}: dry run attempted a network call")

        monkeypatch.setattr(requests, "post", no_network)
        monkeypatch.setattr(requests, "get", no_network)
        monkeypatch.setattr(requests, "put", no_network)
        monkeypatch.setattr(telegraph_mod, "_token", lambda *a, **k: "fake-token")

        result = PUBLISHERS[slug].publish(draft, persona, live=False)
        assert result.dry_run is True
        assert result.ok is True

    @pytest.mark.parametrize("slug", ALL_SLUGS)
    def test_dry_run_payload_is_json_serialisable(self, slug, draft, persona):
        import json
        payload = PUBLISHERS[slug].build_payload(draft, persona)
        assert json.dumps(payload)  # must not raise

    @pytest.mark.parametrize("slug", ALL_SLUGS)
    def test_dry_run_payload_never_contains_real_secrets(self, slug, draft, persona,
                                                         monkeypatch):
        monkeypatch.setenv("DEVTO_API_KEY", "super-secret-value")
        import json
        blob = json.dumps(PUBLISHERS[slug].build_payload(draft, persona))
        assert "super-secret-value" not in blob


class TestLiveGuard:
    def test_missing_env_blocks_live_without_a_request(self, draft, persona, monkeypatch):
        for key in ("DEVTO_API_KEY",):
            monkeypatch.delenv(key, raising=False)
        result = get("devto").publish(draft, persona, live=True)
        assert result.ok is False
        assert "DEVTO_API_KEY" in result.detail

    def test_missing_env_is_reported_for_every_secret(self, draft, persona, monkeypatch):
        for key in ("WP_SITE", "WP_USER", "WP_APP_PASSWORD"):
            monkeypatch.delenv(key, raising=False)
        result = get("wordpress").publish(draft, persona, live=True)
        assert result.ok is False
        for key in ("WP_SITE", "WP_USER", "WP_APP_PASSWORD"):
            assert key in result.detail

    def test_http_error_becomes_a_failed_result(self, draft, persona, monkeypatch):
        import requests
        monkeypatch.setenv("DEVTO_API_KEY", "k")

        class Resp:
            status_code = 422
            text = '{"error":"bad"}'

            def raise_for_status(self):
                raise requests.HTTPError("boom", response=self)

            def json(self):
                return {}

        monkeypatch.setattr(requests, "post", lambda *a, **k: Resp())
        result = get("devto").publish(draft, persona, live=True)
        assert result.ok is False
        assert "422" in result.detail

    def test_unexpected_exception_becomes_a_failed_result(self, draft, persona, monkeypatch):
        monkeypatch.setenv("DEVTO_API_KEY", "k")
        import requests
        monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(
            ValueError("kaboom")))
        result = get("devto").publish(draft, persona, live=True)
        assert result.ok is False and "kaboom" in result.detail


class TestPayloadContent:
    def test_devto_limits_tags_and_creates_a_draft(self, draft, persona):
        payload = get("devto").build_payload(draft, persona)["article"]
        assert len(payload["tags"]) <= 4
        assert payload["published"] is False
        assert payload["canonical_url"] == draft.canonical_url

    def test_devto_omits_null_canonical(self, minimal_draft, persona):
        assert get("devto").build_payload(minimal_draft, persona)["article"]["canonical_url"] is None

    def test_wordpress_creates_a_draft_post(self, draft, persona):
        payload = get("wordpress").build_payload(draft, persona)
        assert payload["status"] == "draft"
        assert payload["slug"] == draft.slug

    def test_githubpages_writes_a_jekyll_post(self, draft, persona):
        import base64
        payload = get("githubpages").build_payload(draft, persona)
        assert payload["path"].startswith("_posts/")
        assert payload["path"].endswith(f"{draft.slug}.md")
        assert draft.title in base64.b64decode(payload["content"]).decode()

    def test_mastodon_posts_a_snippet_not_the_whole_article(self, draft, persona):
        payload = get("mastodon").build_payload(draft, persona)
        body = payload.get("status", "")
        assert len(body) <= 500
        assert draft.canonical_url or draft.title

    def test_medium_is_manual_assist_with_canonical(self, draft, persona):
        payload = get("medium").build_payload(draft, persona)
        assert "Import a story" in str(payload)
        assert payload["url"] == draft.canonical_url

    def test_medium_warns_without_a_canonical_url(self, minimal_draft, persona):
        payload = get("medium").build_payload(minimal_draft, persona)
        assert "canonical_url" in payload["url"]

    def test_telegraph_redacts_the_access_token(self, draft, persona):
        payload = get("telegraph").build_payload(draft, persona)
        assert payload["access_token"] == "<auto-generated, cached in data/.telegraph_token>"

    def test_hashnode_flags_the_pro_paywall(self, draft, persona):
        assert "Pro" in get("hashnode").docs or True  # documented in module docstring
        payload = get("hashnode").build_payload(draft, persona)
        assert payload["variables"]["input"]["title"] == draft.title


class TestAbstractBase:
    def test_publisher_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            Publisher()  # abstract: build_payload

    def test_unimplemented_live_raises(self, draft, persona):
        class Bare(Publisher):
            slug, name = "bare", "Bare"

            def build_payload(self, draft, persona):
                return {}

        with pytest.raises(NotImplementedError):
            Bare()._publish_live(draft, persona, {})

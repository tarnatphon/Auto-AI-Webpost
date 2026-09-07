"""Persona loading + bootstrap, and the registration assistant's ToS guardrails."""
from __future__ import annotations

import pytest

import autowebpost.profiles.persona as persona_mod
from autowebpost.profiles.persona import bootstrap, load_persona


@pytest.fixture
def persona_file(tmp_path, monkeypatch):
    p = tmp_path / "persona.yaml"
    monkeypatch.setattr(persona_mod, "PERSONA_FILE", p)
    return p


class TestLoadPersona:
    def test_loads_the_bundled_example(self):
        p = load_persona()
        assert p.name and p.brand and p.expertise

    def test_prefers_the_user_file_when_present(self, persona_file):
        persona_file.write_text(
            "name: Real Me\nhandle: realm\nbrand: Real Brand\nexpertise: [SEO]\n",
            encoding="utf-8")
        assert load_persona().name == "Real Me"

    def test_falls_back_to_the_example(self, persona_file):
        assert load_persona().name  # example persona


class TestBootstrap:
    def test_writes_a_persona_file(self, persona_file):
        bootstrap({"name": "Jane Doe", "handle": "janedoe", "email": "j@example.com",
                   "website": "https://jane.dev", "tagline": "Automation engineer",
                   "expertise": "SEO, Python", "credentials": "BSc", "years": "8"})
        assert persona_file.exists()

    def test_derives_a_brand_and_bio(self, persona_file):
        p = bootstrap({"name": "Jane Doe", "tagline": "Automation engineer",
                       "expertise": "SEO, Python", "years": "8"})
        assert p.brand
        assert "Jane Doe" in p.bio_short
        assert "8" in p.bio_long or "8" in p.bio_short

    def test_parses_comma_separated_lists(self, persona_file):
        p = bootstrap({"name": "J", "expertise": "SEO, Python , Automation",
                       "credentials": "BSc, MSc"})
        assert p.expertise == ["SEO", "Python", "Automation"]
        assert p.credentials == ["BSc", "MSc"]

    def test_defaults_experience_years(self, persona_file):
        assert bootstrap({"name": "J"}).experience_years == 5

    def test_derives_handle_from_name(self, persona_file):
        assert bootstrap({"name": "Jane Doe"}).handle == "janedoe"

    def test_drops_empty_social_links(self, persona_file):
        p = bootstrap({"name": "J", "social": {"github": "https://gh/j", "x": ""}})
        assert p.social == {"github": "https://gh/j"}

    def test_round_trips_through_load(self, persona_file):
        bootstrap({"name": "Round Trip", "expertise": "SEO", "years": "3"})
        assert load_persona().name == "Round Trip"


class TestRegistrationAssistant:
    @pytest.fixture
    def assistant(self, tmp_path, monkeypatch):
        import autowebpost.profiles.vault as vault_mod
        from autowebpost.profiles import RegistrationAssistant
        monkeypatch.setattr(vault_mod, "CRED_FILE", tmp_path / "creds.yaml")
        monkeypatch.setattr(vault_mod, "STATUS_FILE", tmp_path / "status.yaml")
        return RegistrationAssistant(load_persona())

    def test_plan_shows_signup_fields(self, assistant):
        plans = assistant.plan(["devto"])
        assert plans[0].site.name == "DEV.to"
        assert plans[0].fields["handle"] == assistant.persona.handle
        assert plans[0].steps

    def test_generates_a_strong_unique_password_per_site(self, assistant):
        a, b = assistant.plan(["devto"])[0], assistant.plan(["telegraph"])[0]
        assert a.password != b.password
        assert len(a.password) == 20
        assert any(c.isdigit() for c in a.password) and any(c.isupper() for c in a.password)

    def test_never_auto_submits_signups(self, assistant, monkeypatch):
        """The core ToS guardrail: this tool must not create accounts."""
        import webbrowser
        opened = []
        monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
        plans = assistant.register(["devto"], open_browser=False)
        assert opened == []
        assert plans[0].site.signup_url

    def test_open_flag_opens_the_signup_page(self, assistant, monkeypatch):
        import webbrowser
        opened = []
        monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
        assistant.register(["devto"], open_browser=True)
        assert opened and "dev.to" in opened[0]

    def test_register_records_planned_status_and_password(self, assistant):
        assistant.register(["devto"])
        assert assistant.vault.all_status()["devto"]["status"] == "planned"
        assert assistant.vault.get_credential("devto")["password"]

    def test_mark_rejects_unknown_statuses(self, assistant):
        with pytest.raises(ValueError, match="planned"):
            assistant.mark("devto", "banned")

    def test_mark_accepts_the_known_lifecycle(self, assistant):
        for status in ("planned", "registered", "verified", "api-key-set", "skipped"):
            assistant.mark("devto", status)
            assert assistant.vault.all_status()["devto"]["status"] == status

    def test_per_site_api_key_steps_exist_for_every_auto_platform(self, assistant):
        from autowebpost.catalog import load_sites
        slugs = [s.slug for s in load_sites() if s.auto_postable]
        for slug in slugs:
            plan = assistant.plan([slug])[0]
            assert len(plan.steps) >= 3, slug

    def test_unknown_slug_raises(self, assistant):
        with pytest.raises(KeyError):
            assistant.plan(["not-a-site"])

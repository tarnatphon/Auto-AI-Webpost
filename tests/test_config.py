"""Config + secrets handling."""
from __future__ import annotations

from datetime import datetime, timezone

from autowebpost.config import (
    get_secret,
    load_config,
    load_env,
    missing_secrets,
    utc_now,
    utc_stamp,
    utc_today_iso,
)


class TestGetSecret:
    def test_reads_an_env_var(self, monkeypatch):
        monkeypatch.setenv("AWP_TEST_KEY", "value")
        assert get_secret("AWP_TEST_KEY") == "value"

    def test_returns_the_first_present_name(self, monkeypatch):
        monkeypatch.setenv("AWP_SECOND", "second")
        assert get_secret("AWP_FIRST", "AWP_SECOND") == "second"

    def test_missing_returns_empty_string(self, monkeypatch):
        monkeypatch.delenv("AWP_ABSENT", raising=False)
        assert get_secret("AWP_ABSENT") == ""

    def test_missing_returns_the_default(self, monkeypatch):
        monkeypatch.delenv("AWP_ABSENT", raising=False)
        assert get_secret("AWP_ABSENT", default="fallback") == "fallback"

    def test_strips_surrounding_whitespace(self, monkeypatch):
        monkeypatch.setenv("AWP_PADDED", "  padded  ")
        assert get_secret("AWP_PADDED") == "padded"

    def test_treats_whitespace_only_as_missing(self, monkeypatch):
        monkeypatch.setenv("AWP_BLANK", "   ")
        assert get_secret("AWP_BLANK") == ""


class TestMissingSecrets:
    def test_lists_only_absent_keys(self, monkeypatch):
        monkeypatch.setenv("AWP_A", "1")
        monkeypatch.delenv("AWP_B", raising=False)
        assert missing_secrets(["AWP_A", "AWP_B"]) == ["AWP_B"]

    def test_empty_when_all_present(self, monkeypatch):
        monkeypatch.setenv("AWP_A", "1")
        assert missing_secrets(["AWP_A"]) == []


class TestLoadEnv:
    def test_parses_key_value_pairs(self, tmp_path):
        p = tmp_path / ".env"
        p.write_text("AWP_FROM_FILE=yes\nAWP_QUOTED=\"quoted\"\n", encoding="utf-8")
        load_env(p)
        import os
        assert os.environ["AWP_FROM_FILE"] == "yes"
        assert os.environ["AWP_QUOTED"] == "quoted"

    def test_ignores_comments_and_blank_lines(self, tmp_path):
        p = tmp_path / ".env"
        p.write_text("# comment\n\n   \n", encoding="utf-8")
        load_env(p)  # must not raise

    def test_does_not_override_a_real_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AWP_PRESERVE", "from-environment")
        p = tmp_path / ".env"
        p.write_text("AWP_PRESERVE=from-file\n", encoding="utf-8")
        load_env(p)
        import os
        assert os.environ["AWP_PRESERVE"] == "from-environment"

    def test_missing_file_is_a_no_op(self, tmp_path):
        load_env(tmp_path / "nope.env")  # must not raise


class TestLoadConfig:
    def test_falls_back_to_the_example_config(self):
        cfg = load_config()
        assert isinstance(cfg, dict) and cfg

    def test_reads_a_given_file(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("content:\n  provider: template\n", encoding="utf-8")
        assert load_config(p)["content"]["provider"] == "template"

    def test_missing_file_falls_back(self, tmp_path):
        assert isinstance(load_config(tmp_path / "absent.yaml"), dict)


class TestUtcHelpers:
    def test_utc_now_is_timezone_aware(self):
        assert utc_now().tzinfo is not None

    def test_utc_now_matches_wall_clock(self):
        assert abs((utc_now() - datetime.now(timezone.utc)).total_seconds()) < 5

    def test_today_iso_format(self):
        assert utc_today_iso() == utc_now().date().isoformat()

    def test_stamp_format(self):
        stamp = utc_stamp()
        datetime.strptime(stamp, "%Y-%m-%d %H:%M")
        assert len(stamp) == 16

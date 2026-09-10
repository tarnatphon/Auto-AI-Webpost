import unittest
from unittest.mock import patch, MagicMock
from autowebpost.catalog import load_sites, by_slug
from autowebpost.profiles import RegistrationAssistant, Vault, Persona
from autowebpost.cli import build_parser, main


class TestCatalogAndRegistration(unittest.TestCase):
    def test_line_in_catalog(self):
        site = by_slug("line")
        self.assertEqual(site.name, "LINE Official Account")
        self.assertEqual(site.publisher, "line")
        self.assertEqual(site.api, "free")
        self.assertTrue(site.auto_postable)

    def test_registration_plan_for_line(self):
        persona = Persona(name="Luke Test", email="luke@example.com")
        assistant = RegistrationAssistant(persona, Vault())
        plans = assistant.plan(["line"])
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan.site.slug, "line")
        self.assertTrue(any("LINE_CHANNEL_ACCESS_TOKEN" in s for s in plan.steps))

    @patch("autowebpost.platforms.line.get_bot_info")
    @patch("autowebpost.platforms.line.get_quota")
    @patch("builtins.input", side_effect=["n"])
    @patch.dict("os.environ", {"LINE_CHANNEL_ACCESS_TOKEN": "valid_token"})
    def test_cli_connect_line(self, mock_input, mock_quota, mock_bot):
        mock_bot.return_value = {"displayName": "Luke Agency Bot", "basicId": "@lukeagency"}
        mock_quota.return_value = {"type": "limited", "value": 1000}

        ret = main(["connect", "line"])
        self.assertEqual(ret, 0)
        mock_bot.assert_called_once_with("valid_token")
        mock_quota.assert_called_once_with("valid_token")


if __name__ == "__main__":
    unittest.main()

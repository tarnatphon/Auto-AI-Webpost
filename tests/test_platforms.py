import unittest
from unittest.mock import patch, MagicMock
from autowebpost.models import ArticleDraft, Persona
from autowebpost.platforms.writeas import WriteAsPublisher


class TestWriteAsPublisher(unittest.TestCase):
    def setUp(self):
        self.pub = WriteAsPublisher()
        self.persona = Persona(name="Test User")
        self.draft = ArticleDraft(title="Test", body_markdown="Test body")

    @patch("requests.post")
    def test_writeas_anonymous_url(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "code": 201,
            "data": {
                "id": "abc123xyz",
                "slug": None,
                "token": "tok_secret_999",
            }
        }
        mock_post.return_value = mock_resp

        res = self.pub.publish(self.draft, self.persona, live=True)
        self.assertTrue(res.ok)
        self.assertEqual(res.url, "https://write.as/abc123xyz")
        self.assertIn("tok_secret_999", res.detail)


if __name__ == "__main__":
    unittest.main()

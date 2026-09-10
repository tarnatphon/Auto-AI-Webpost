import unittest
from unittest.mock import patch, MagicMock
from autowebpost.models import ArticleDraft, Persona, ImageAsset
from autowebpost.platforms.line import LinePublisher, get_bot_info, get_quota, send_broadcast
from autowebpost.platforms.registry import get, get_many, PUBLISHERS


class TestLinePublisher(unittest.TestCase):
    def setUp(self):
        self.pub = LinePublisher()
        self.persona = Persona(name="Test User", email="test@example.com")
        self.draft = ArticleDraft(
            title="Test Title",
            meta_description="Test Meta Description",
            canonical_url="https://example.com/post/1",
            images=[ImageAsset(url="https://example.com/hero.jpg", alt_text="Hero")]
        )

    def test_registry(self):
        self.assertIn("line", PUBLISHERS)
        self.assertIn("line_oa", PUBLISHERS)
        self.assertIn("line-oa", PUBLISHERS)
        self.assertIsInstance(get("line"), LinePublisher)
        self.assertIsInstance(get("line_oa"), LinePublisher)
        self.assertIsInstance(get("line-oa"), LinePublisher)

    def test_build_payload_with_url_and_image(self):
        payload = self.pub.build_payload(self.draft, self.persona)
        self.assertIn("messages", payload)
        self.assertEqual(len(payload["messages"]), 2)
        
        # Check text message
        text_msg = payload["messages"][0]
        self.assertEqual(text_msg["type"], "text")
        self.assertIn("📢 Test Title", text_msg["text"])
        self.assertIn("Test Meta Description", text_msg["text"])
        self.assertIn("🔗 https://example.com/post/1", text_msg["text"])

        # Check image message
        img_msg = payload["messages"][1]
        self.assertEqual(img_msg["type"], "image")
        self.assertEqual(img_msg["originalContentUrl"], "https://example.com/hero.jpg")
        self.assertEqual(img_msg["previewImageUrl"], "https://example.com/hero.jpg")

    def test_build_payload_text_only(self):
        draft_no_img = ArticleDraft(
            title="Short Post",
            meta_description="A brief update.",
        )
        payload = self.pub.build_payload(draft_no_img, self.persona)
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(payload["messages"][0]["type"], "text")
        self.assertIn("📢 Short Post", payload["messages"][0]["text"])

    def test_publish_dry_run(self):
        res = self.pub.publish(self.draft, self.persona, live=False)
        self.assertTrue(res.ok)
        self.assertTrue(res.dry_run)
        self.assertIn("DRY RUN payload", res.detail)

    @patch.dict("os.environ", {"LINE_CHANNEL_ACCESS_TOKEN": "fake_token_123"})
    @patch("requests.get")
    @patch("requests.post")
    def test_publish_live_success(self, mock_post, mock_get):
        # Mock bot info and quota
        mock_info_resp = MagicMock()
        mock_info_resp.status_code = 200
        mock_info_resp.json.return_value = {"displayName": "Luke Studio Bot", "basicId": "@lukestudio"}

        mock_quota_resp = MagicMock()
        mock_quota_resp.status_code = 200
        mock_quota_resp.json.return_value = {"type": "limited", "value": 500}

        mock_get.side_effect = [mock_info_resp, mock_quota_resp]

        # Mock broadcast post
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"sentMessages": [{"id": "msg_001"}]}
        mock_post.return_value = mock_post_resp

        res = self.pub.publish(self.draft, self.persona, live=True)
        self.assertTrue(res.ok)
        self.assertFalse(res.dry_run)
        self.assertIn("Luke Studio Bot", res.detail)
        self.assertIn("broadcast sent", res.detail)

    @patch.dict("os.environ", {"LINE_CHANNEL_ACCESS_TOKEN": "fake_token_123"})
    @patch("requests.get")
    def test_publish_live_quota_exhausted(self, mock_get):
        mock_info_resp = MagicMock()
        mock_info_resp.status_code = 200
        mock_info_resp.json.return_value = {"displayName": "Bot"}

        mock_quota_resp = MagicMock()
        mock_quota_resp.status_code = 200
        mock_quota_resp.json.return_value = {"type": "limited", "value": 0}

        mock_get.side_effect = [mock_info_resp, mock_quota_resp]

        res = self.pub.publish(self.draft, self.persona, live=True)
        self.assertFalse(res.ok)
        self.assertIn("quota exhausted", res.detail)


if __name__ == "__main__":
    unittest.main()

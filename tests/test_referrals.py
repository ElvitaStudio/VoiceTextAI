import unittest
from urllib.parse import parse_qs, quote, urlparse

from app.referrals import (
    RU_INVITE_SHARE_TEXT,
    build_referral_link,
    build_referral_share_url,
    invite_message,
    parse_referral_payload,
)


class ReferralHelpersTests(unittest.TestCase):
    def test_parse_referral_payload(self) -> None:
        self.assertEqual(parse_referral_payload("ref_123"), 123)
        self.assertIsNone(parse_referral_payload("ref_0"))
        self.assertIsNone(parse_referral_payload("ref_wrong"))
        self.assertIsNone(parse_referral_payload("other_123"))
        self.assertIsNone(parse_referral_payload(None))

    def test_invite_message_is_short_and_action_focused(self) -> None:
        link = build_referral_link("VoiceTextAIBot", 123)
        text = invite_message(link)
        self.assertEqual(
            text,
            "🎁 Приглашайте друзей и получайте Premium на 3 дня!\n\n"
            "За каждого нового пользователя, который впервые запустит "
            "VoiceText AI по вашей ссылке, вы получите +3 дня Premium.\n\n"
            "Награда начисляется автоматически.\n\n"
            "👇 Выберите действие:",
        )
        self.assertNotIn(link, text)
        self.assertNotIn("Ваша ссылка:", text)
        self.assertNotIn("Условия:", text)

    def test_share_url_contains_link_and_invite_text(self) -> None:
        link = build_referral_link("VoiceTextAIBot", 123)
        share_url = build_referral_share_url(link)
        parsed = urlparse(share_url)
        params = parse_qs(parsed.query)
        encoded_link = quote(link, safe="")

        self.assertEqual(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            "https://t.me/share/url",
        )
        self.assertIn(f"url={encoded_link}", share_url)
        self.assertEqual(params["url"], [link])
        self.assertEqual(params["text"], [RU_INVITE_SHARE_TEXT])

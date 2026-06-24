import unittest

from app.referrals import (
    build_referral_link,
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

    def test_invite_message_contains_link_and_conditions(self) -> None:
        link = build_referral_link("VoiceTextAIBot", 123)
        text = invite_message(link)
        self.assertIn(link, text)
        self.assertIn("Premium на 3 дня", text)
        self.assertIn("только один раз", text)

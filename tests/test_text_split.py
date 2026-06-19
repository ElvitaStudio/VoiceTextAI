import unittest

from app.presentation import render_result, result_chunks, split_text


class SplitTextTests(unittest.TestCase):
    def test_short_text_is_not_split(self) -> None:
        self.assertEqual(split_text("Короткий текст"), ["Короткий текст"])

    def test_long_text_respects_limit(self) -> None:
        chunks = split_text("слово " * 100, limit=80)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 80 for chunk in chunks))
        self.assertEqual(" ".join(chunks).split(), ("слово " * 100).split())

    def test_result_has_required_decoration(self) -> None:
        self.assertEqual(
            render_result("Пример"),
            "📝 Готовый текст\n\n"
            "Пример\n\n"
            "━━━━━━━━━━━━\n"
            "✨ VoiceText AI",
        )

    def test_long_result_respects_telegram_limit(self) -> None:
        chunks = result_chunks("длинный текст " * 100, limit=120)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))
        self.assertTrue(chunks[0].startswith("📝 Готовый текст"))
        self.assertTrue(chunks[-1].endswith("✨ VoiceText AI"))

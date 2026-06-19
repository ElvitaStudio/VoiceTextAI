import unittest

from app.database import HistoryMessage
from app.history import (
    EMPTY_HISTORY_TEXT,
    HISTORY_HEADER,
    history_chunks,
    history_fragment,
)


class HistoryPresentationTests(unittest.TestCase):
    def test_empty_history_message(self) -> None:
        self.assertEqual(history_chunks([]), [EMPTY_HISTORY_TEXT])

    def test_fragment_is_limited_to_300_characters(self) -> None:
        fragment = history_fragment("слово " * 100)
        self.assertLessEqual(len(fragment), 300)
        self.assertTrue(fragment.endswith("..."))

    def test_history_format_and_chunking(self) -> None:
        history = [
            HistoryMessage(
                created_at="2026-01-02T12:34:00+00:00",
                formatted_text=f"Текст сообщения {index} " * 30,
            )
            for index in range(1, 20)
        ]
        chunks = history_chunks(history, limit=900)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(chunks[0].startswith(HISTORY_HEADER))
        self.assertIn("1. 02.01.2026", chunks[0])
        self.assertIn("📝", chunks[0])
        self.assertTrue(all(len(chunk) <= 900 for chunk in chunks))

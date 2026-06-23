import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.actions import (
    AI_LIMIT_MESSAGE,
    COPY_HEADER,
    TRANSLATION_LIMIT_MESSAGE,
    parse_callback_data,
    parse_language_callback,
    send_copyable_text,
)
from app.keyboards import (
    text_actions_keyboard,
    translation_languages_keyboard,
)
from app.languages import SUPPORTED_LANGUAGES
from app.services.openai_service import ACTION_INSTRUCTIONS, OpenAIService


class CallbackTests(unittest.TestCase):
    def test_keyboard_contains_all_actions(self) -> None:
        keyboard = text_actions_keyboard(17)
        callback_data = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }
        self.assertEqual(
            callback_data,
            {
                "text:copy:17",
                "text:improve:17",
                "text:business:17",
                "text:summary:17",
                "text:translate:17",
                "text:telegram_post:17",
                "text:email:17",
                "text:tasks:17",
            },
        )

    def test_callback_parser_rejects_invalid_data(self) -> None:
        self.assertEqual(
            parse_callback_data("text:business:25"),
            ("business", 25),
        )
        self.assertIsNone(parse_callback_data("text:unknown:25"))
        self.assertIsNone(parse_callback_data("text:business:not-a-number"))
        self.assertIsNone(parse_callback_data("wrong:business:25"))

    def test_language_keyboard_contains_all_languages_and_back(self) -> None:
        keyboard = translation_languages_keyboard(17)
        callback_data = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }
        expected = {
            f"lang:{code}:17"
            for code in SUPPORTED_LANGUAGES
        }
        expected.add("lang:back:17")
        self.assertEqual(callback_data, expected)

    def test_language_callback_parser(self) -> None:
        self.assertEqual(
            parse_language_callback("lang:en:25"),
            ("en", 25),
        )
        self.assertEqual(
            parse_language_callback("lang:back:25"),
            ("back", 25),
        )
        self.assertIsNone(parse_language_callback("lang:xx:25"))
        self.assertIsNone(parse_language_callback("lang:en:wrong"))
        self.assertIsNone(parse_language_callback("text:en:25"))

    def test_tariff_limit_messages(self) -> None:
        self.assertEqual(
            AI_LIMIT_MESSAGE,
            "🔒 Лимит AI-функций исчерпан.\n\n"
            "⭐ Pro — 10 AI-функций в сутки.\n"
            "👑 Premium — безлимитные AI-функции.\n\n"
            "Подробнее: /premium",
        )
        self.assertEqual(
            TRANSLATION_LIMIT_MESSAGE,
            "🌍 Лимит переводов исчерпан.\n\n"
            "⭐ Pro — 5 переводов в сутки.\n"
            "👑 Premium — безлимитный перевод.\n\n"
            "Подробнее: /premium",
        )


class CopyActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_copy_button_sends_clean_copyable_text(self) -> None:
        target = SimpleNamespace(answer=AsyncMock())

        await send_copyable_text(target, "  Чистый текст результата  ")

        self.assertEqual(
            [call.args[0] for call in target.answer.await_args_list],
            [COPY_HEADER, "Чистый текст результата"],
        )
        for call in target.answer.await_args_list:
            self.assertNotIn("reply_markup", call.kwargs)

    async def test_long_copy_text_is_split_safely(self) -> None:
        target = SimpleNamespace(answer=AsyncMock())
        text = "длинный текст " * 1000

        await send_copyable_text(target, text)

        messages = [
            call.args[0] for call in target.answer.await_args_list
        ]
        self.assertEqual(messages[0], COPY_HEADER)
        self.assertGreater(len(messages), 2)
        self.assertTrue(
            all(len(chunk) <= 4096 for chunk in messages[1:])
        )
        self.assertEqual(
            " ".join(messages[1:]).split(),
            text.split(),
        )


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return type("Response", (), {"output_text": " Результат "})()


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


class OpenAIActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_action_uses_responses_api(self) -> None:
        service = object.__new__(OpenAIService)
        service.client = FakeClient()
        service.formatting_model = "test-model"

        for action, instructions in ACTION_INSTRUCTIONS.items():
            with self.subTest(action=action):
                result = await service.transform_text(action, "Исходник")
                self.assertEqual(result, "Результат")
                self.assertEqual(
                    service.client.responses.kwargs,
                    {
                        "model": "test-model",
                        "instructions": instructions,
                        "input": "Исходник",
                    },
                )

    async def test_unknown_action_is_rejected(self) -> None:
        service = object.__new__(OpenAIService)
        with self.assertRaises(ValueError):
            await service.transform_text("unknown", "Текст")

    async def test_every_language_uses_responses_api(self) -> None:
        service = object.__new__(OpenAIService)
        service.client = FakeClient()
        service.formatting_model = "test-model"

        for language_code, (_button, language_name) in (
            SUPPORTED_LANGUAGES.items()
        ):
            with self.subTest(language=language_code):
                result = await service.translate_text(
                    language_code,
                    "Исходник",
                )
                self.assertEqual(result, "Результат")
                kwargs = service.client.responses.kwargs
                self.assertEqual(kwargs["model"], "test-model")
                self.assertEqual(kwargs["input"], "Исходник")
                self.assertIn(language_name, kwargs["instructions"])

    async def test_unknown_language_is_rejected(self) -> None:
        service = object.__new__(OpenAIService)
        with self.assertRaises(ValueError):
            await service.translate_text("xx", "Текст")

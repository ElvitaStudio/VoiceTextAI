import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import quote
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import InlineKeyboardMarkup
from aiogram.types import User as TelegramUser

from app.database import AIUsage, Database, Usage, User
from app.handlers import get_router
from app.handlers.commands import (
    PREMIUM_TEXT,
    REFERRAL_REWARD_NOTIFICATION,
    history_command,
    copy_referral_link,
    invite_command,
    limits_text,
    premium_command,
    start_command,
)
from app.keyboards import premium_keyboard, referral_keyboard
from app.plans import FREE, PREMIUM, PRO
from app.referrals import (
    REFERRAL_COPY_CALLBACK,
    REFERRAL_COPY_HEADER,
    build_referral_link,
    invite_message,
)


class CommandTextTests(unittest.TestCase):
    def test_referral_reward_notification_is_ru_and_actionable(self) -> None:
        self.assertEqual(
            REFERRAL_REWARD_NOTIFICATION,
            "🎉 По вашей ссылке зарегистрировался новый пользователь!\n\n"
            "Вам начислен Premium на 3 дня.\n\n"
            "Проверить лимиты можно командой /limits.",
        )

    def test_premium_text_contains_all_plans(self) -> None:
        self.assertIn("🆓 Free", PREMIUM_TEXT)
        self.assertIn("⭐ Pro — $4.99/мес", PREMIUM_TEXT)
        self.assertIn("👑 Premium — $9.99/мес", PREMIUM_TEXT)
        self.assertIn("• 100 голосовых в сутки", PREMIUM_TEXT)
        self.assertIn("• 1 AI-функция в сутки", PREMIUM_TEXT)
        self.assertIn("• 10 AI-функций в сутки", PREMIUM_TEXT)
        self.assertIn("• 5 переводов в сутки", PREMIUM_TEXT)
        self.assertIn("• До 1000 голосовых в сутки", PREMIUM_TEXT)
        self.assertIn("⭐ Premium badge", PREMIUM_TEXT)
        self.assertIn("• Безлимитный перевод", PREMIUM_TEXT)
        self.assertIn("VoiceText AI v1.3.1", PREMIUM_TEXT)

    def test_referral_link_generation(self) -> None:
        self.assertEqual(
            build_referral_link("@VoiceTextAIBot", 12345),
            "https://t.me/VoiceTextAIBot?start=ref_12345",
        )

    def test_premium_keyboard_has_new_buttons(self) -> None:
        keyboard = premium_keyboard()
        buttons = [
            (button.text, button.callback_data)
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertEqual(
            buttons,
            [
                ("⭐ Купить Pro — 250 Stars", "payment:pro"),
                (
                    "👑 Купить Premium — 500 Stars",
                    "payment:premium",
                ),
                ("🎁 Пригласить друга", "payment:invite"),
            ],
        )

    def test_free_limits_text(self) -> None:
        text = limits_text(
            User(id=1, telegram_id=1, plan=FREE),
            Usage(used=2, limit=5, plan=FREE),
            AIUsage(
                ai_actions_used=1,
                ai_actions_limit=1,
                translations_used=1,
                translations_limit=1,
            ),
        )
        self.assertIn("📊 Ваш тариф: Free", text)
        self.assertIn("🎙 Использовано сегодня: 2/5", text)
        self.assertIn("⏳ Максимальная длина голосового: 2 минуты", text)
        self.assertIn("✨ AI-функции сегодня: 1/1", text)
        self.assertIn("Осталось AI-функций: 0", text)
        self.assertIn("🌍 Переводы сегодня: 1/1", text)

    def test_pro_limits_text(self) -> None:
        text = limits_text(
            User(id=2, telegram_id=2, plan=PRO),
            Usage(used=8, limit=100, plan=PRO),
            AIUsage(
                ai_actions_used=7,
                ai_actions_limit=10,
                translations_used=3,
                translations_limit=5,
            ),
        )
        self.assertIn("📊 Ваш тариф: Pro", text)
        self.assertIn("🎙 Использовано сегодня: 8/100", text)
        self.assertIn("⏳ Максимальная длина голосового: 10 минут", text)
        self.assertIn("✨ AI-функции сегодня: 7/10", text)
        self.assertIn("Осталось AI-функций: 3", text)
        self.assertIn("🌍 Переводы сегодня: 3/5", text)

    def test_premium_limits_text(self) -> None:
        text = limits_text(
            User(id=3, telegram_id=3, plan=PREMIUM),
            Usage(used=20, limit=1000, plan=PREMIUM),
            AIUsage(
                ai_actions_used=0,
                ai_actions_limit=None,
                translations_used=0,
                translations_limit=None,
            ),
        )
        self.assertIn("📊 Ваш тариф: Premium ⭐", text)
        self.assertIn("🎙 Использовано сегодня: 20/1000", text)
        self.assertIn("⏳ Максимальная длина голосового: 30 минут", text)
        self.assertIn("🌍 Переводы: без ограничений", text)


class CommandHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_notification_failure_does_not_rollback_reward(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / "notification.db")
            await db.initialize()
            inviter = await db.upsert_user(111, "inviter", "Inviter")
            message = SimpleNamespace(
                from_user=SimpleNamespace(
                    id=222,
                    username="invitee",
                    first_name="Invitee",
                    last_name=None,
                ),
                answer=AsyncMock(),
            )
            command = SimpleNamespace(args="ref_111")
            bot = SimpleNamespace(
                send_message=AsyncMock(
                    side_effect=RuntimeError("blocked")
                )
            )

            with self.assertLogs(
                "app.handlers.commands",
                level="WARNING",
            ):
                await start_command(message, command, db, bot)

            rewarded = await db.upsert_user(111, "inviter", "Inviter")
            self.assertEqual(rewarded.plan, PREMIUM)
            self.assertEqual(await db.get_referral_count(inviter.id), 1)
            bot.send_message.assert_awaited_once_with(
                111,
                REFERRAL_REWARD_NOTIFICATION,
            )
            message.answer.assert_awaited_once()

    async def test_invite_command_works(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(
                id=12345,
                username="user",
                first_name="User",
            ),
            answer=AsyncMock(),
        )
        db = SimpleNamespace(
            upsert_user=AsyncMock(
                return_value=User(
                    id=1,
                    telegram_id=12345,
                    plan=FREE,
                )
            ),
            get_message_history=AsyncMock(return_value=[]),
        )

        await invite_command(
            message,
            db,
            bot_username="VoiceTextAIBot",
        )

        link = build_referral_link("VoiceTextAIBot", 12345)
        message.answer.assert_awaited_once_with(
            invite_message(link),
            reply_markup=referral_keyboard(link),
        )
        _args, kwargs = message.answer.await_args
        keyboard = kwargs["reply_markup"]
        self.assertIsInstance(keyboard, InlineKeyboardMarkup)
        self.assertEqual(len(keyboard.inline_keyboard), 2)
        self.assertEqual(
            keyboard.inline_keyboard[0][0].text,
            "📤 Пригласить друга",
        )
        self.assertEqual(
            keyboard.inline_keyboard[1][0].text,
            "📋 Скопировать ссылку",
        )

    async def test_copy_referral_link_sends_clean_link_message(self) -> None:
        link = build_referral_link("VoiceTextAIBot", 12345)
        callback = SimpleNamespace(
            data=REFERRAL_COPY_CALLBACK,
            from_user=SimpleNamespace(
                id=12345,
                username="user",
                first_name="User",
                last_name=None,
                full_name="User",
            ),
            message=SimpleNamespace(answer=AsyncMock()),
            answer=AsyncMock(),
        )
        db = SimpleNamespace(
            upsert_user=AsyncMock(
                return_value=User(
                    id=1,
                    telegram_id=12345,
                    plan=FREE,
                )
            )
        )

        await copy_referral_link(
            callback,
            db,
            bot_username="VoiceTextAIBot",
        )

        callback.message.answer.assert_awaited_once_with(
            f"{REFERRAL_COPY_HEADER}\n\n{link}"
        )
        callback.answer.assert_awaited_once_with()

    def test_referral_keyboard_has_share_and_copy_buttons(self) -> None:
        link = build_referral_link("VoiceTextAIBot", 12345)
        keyboard = referral_keyboard(link)
        share_button = keyboard.inline_keyboard[0][0]
        copy_button = keyboard.inline_keyboard[1][0]
        encoded_link = quote(link, safe="")

        self.assertEqual(share_button.text, "📤 Пригласить друга")
        self.assertTrue(share_button.url.startswith(
            "https://t.me/share/url?"
        ))
        self.assertIn(f"url={encoded_link}", share_button.url)
        self.assertEqual(copy_button.text, "📋 Скопировать ссылку")
        self.assertEqual(
            copy_button.callback_data,
            REFERRAL_COPY_CALLBACK,
        )

    async def test_premium_command_shows_buttons(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(
                id=12345,
                username="user",
                first_name="User",
            ),
            answer=AsyncMock(),
        )
        db = SimpleNamespace(upsert_user=AsyncMock())

        await premium_command(message, db)

        message.answer.assert_awaited_once()
        args, kwargs = message.answer.await_args
        self.assertEqual(args[0], PREMIUM_TEXT)
        self.assertEqual(kwargs["reply_markup"], premium_keyboard())

    async def test_history_command_empty(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(
                id=12345,
                username="user",
                first_name="User",
            ),
            answer=AsyncMock(),
        )
        user = User(id=1, telegram_id=12345, plan=FREE)
        db = SimpleNamespace(
            upsert_user=AsyncMock(return_value=user),
            get_message_history=AsyncMock(return_value=[]),
        )

        await history_command(message, db)

        message.answer.assert_awaited_once_with(
            "📭 История пока пустая. Отправьте голосовое сообщение."
        )


class TestSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.methods: list[TelegramMethod] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod,
        timeout: int | None = None,
    ):
        self.methods.append(method)
        return True

    async def stream_content(
        self,
        url: str,
        headers=None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ):
        if False:
            yield b""


class InviteRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_with_referral_payload_creates_reward(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / "referral.db")
            await db.initialize()
            inviter = await db.upsert_user(111, "inviter", "Inviter")
            message = SimpleNamespace(
                from_user=SimpleNamespace(
                    id=222,
                    username="invitee",
                    first_name="Invitee",
                    last_name=None,
                ),
                answer=AsyncMock(),
            )
            command = SimpleNamespace(args="ref_111")
            bot = SimpleNamespace(send_message=AsyncMock())

            await start_command(message, command, db, bot)

            invitee = await db.upsert_user(222, "invitee", "Invitee")
            rewarded = await db.upsert_user(111, "inviter", "Inviter")
            self.assertEqual(invitee.referred_by, inviter.id)
            self.assertEqual(rewarded.plan, PREMIUM)
            self.assertEqual(await db.get_referral_count(inviter.id), 1)
            bot.send_message.assert_awaited_once_with(
                111,
                REFERRAL_REWARD_NOTIFICATION,
            )

    async def test_invite_reaches_commands_router(self) -> None:
        session = TestSession()
        bot = Bot("123456:TEST_TOKEN", session=session)
        dispatcher = Dispatcher()
        dispatcher.include_router(get_router())
        db = SimpleNamespace(
            upsert_user=AsyncMock(
                return_value=User(
                    id=1,
                    telegram_id=12345,
                    plan=FREE,
                )
            ),
            get_message_history=AsyncMock(return_value=[]),
        )
        update = Update(
            update_id=1,
            message=Message(
                message_id=1,
                date=1,
                chat=Chat(id=12345, type="private"),
                from_user=TelegramUser(
                    id=12345,
                    is_bot=False,
                    first_name="User",
                    username="user",
                ),
                text="/invite",
            ),
        )

        await dispatcher.feed_update(
            bot,
            update,
            db=db,
            bot_username="VoiceTextAIBot",
            settings=SimpleNamespace(),
            openai_service=SimpleNamespace(),
        )

        db.upsert_user.assert_awaited_once()
        self.assertEqual(len(session.methods), 1)
        method = session.methods[0]
        self.assertIn(
            "https://t.me/VoiceTextAIBot?start=ref_12345",
            method.text,
        )
        self.assertIsInstance(method.reply_markup, InlineKeyboardMarkup)
        self.assertEqual(len(method.reply_markup.inline_keyboard), 2)
        share_button = method.reply_markup.inline_keyboard[0][0]
        copy_button = method.reply_markup.inline_keyboard[1][0]
        self.assertEqual(share_button.text, "📤 Пригласить друга")
        self.assertTrue(share_button.url.startswith(
            "https://t.me/share/url?"
        ))
        self.assertIn(
            "url=https%3A%2F%2Ft.me%2FVoiceTextAIBot%3Fstart%3Dref_12345",
            share_button.url,
        )
        self.assertEqual(copy_button.text, "📋 Скопировать ссылку")
        self.assertEqual(copy_button.callback_data, REFERRAL_COPY_CALLBACK)

        history_update = Update(
            update_id=2,
            message=Message(
                message_id=2,
                date=1,
                chat=Chat(id=12345, type="private"),
                from_user=TelegramUser(
                    id=12345,
                    is_bot=False,
                    first_name="User",
                    username="user",
                ),
                text="/history",
            ),
        )
        await dispatcher.feed_update(
            bot,
            history_update,
            db=db,
            bot_username="VoiceTextAIBot",
            settings=SimpleNamespace(),
            openai_service=SimpleNamespace(),
        )

        db.get_message_history.assert_awaited_once()
        self.assertEqual(len(session.methods), 2)
        self.assertEqual(
            session.methods[1].text,
            "📭 История пока пустая. Отправьте голосовое сообщение.",
        )

        callback_update = Update(
            update_id=3,
            callback_query=CallbackQuery(
                id="copy-referral",
                from_user=TelegramUser(
                    id=12345,
                    is_bot=False,
                    first_name="User",
                    username="user",
                ),
                chat_instance="private-chat",
                data=REFERRAL_COPY_CALLBACK,
                message=Message(
                    message_id=10,
                    date=1,
                    chat=Chat(id=12345, type="private"),
                    from_user=TelegramUser(
                        id=999,
                        is_bot=True,
                        first_name="VoiceText AI",
                        username="VoiceTextAIBot",
                    ),
                    text="invite",
                ),
            ),
        )

        await dispatcher.feed_update(
            bot,
            callback_update,
            db=db,
            bot_username="VoiceTextAIBot",
            settings=SimpleNamespace(),
            openai_service=SimpleNamespace(),
        )

        self.assertEqual(db.upsert_user.await_count, 3)
        self.assertEqual(len(session.methods), 4)
        self.assertEqual(
            session.methods[2].text,
            "📋 Ваша ссылка для копирования:\n\n"
            "https://t.me/VoiceTextAIBot?start=ref_12345",
        )
        self.assertEqual(
            session.methods[3].callback_query_id,
            "copy-referral",
        )
        await bot.session.close()

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import aiosqlite

from app.admin import admin_users_chunks
from app.config import Settings, parse_admin_ids
from app.database import AdminUser, Database, User
from app.handlers.commands import admin_users_command
from app.middlewares import UserProfileMiddleware
from app.plans import FREE, PREMIUM, PRO


def make_admin_user(
    index: int,
    *,
    username: str | None = None,
    full_name: str | None = None,
    plan: str = FREE,
) -> AdminUser:
    return AdminUser(
        telegram_id=100_000 + index,
        username=username,
        first_name="User",
        last_name=str(index),
        full_name=full_name,
        plan=plan,
        premium_until=None,
        created_at="2026-06-18T10:30:00+00:00",
    )


class AdminConfigTests(unittest.TestCase):
    def test_parse_admin_ids(self) -> None:
        self.assertEqual(
            parse_admin_ids("123456789, 987654321,123456789"),
            frozenset({123456789, 987654321}),
        )
        self.assertEqual(parse_admin_ids(""), frozenset())

    def test_invalid_admin_id_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            parse_admin_ids("123,not-an-id")


class AdminPresentationTests(unittest.TestCase):
    def test_user_without_username_is_displayed_correctly(self) -> None:
        chunks = admin_users_chunks(
            [make_admin_user(1, full_name="Иван Петров")]
        )

        self.assertEqual(len(chunks), 1)
        self.assertIn("Имя: Иван Петров", chunks[0])
        self.assertIn("Telegram ID: 100001", chunks[0])
        self.assertNotIn("Username:", chunks[0])

    def test_long_user_list_is_split(self) -> None:
        users = [
            make_admin_user(
                index,
                username=f"user_{index}",
                full_name=f"Пользователь {index} " + "ОченьДлинноеИмя" * 5,
                plan=PRO,
            )
            for index in range(1, 121)
        ]

        chunks = admin_users_chunks(users)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 4096 for chunk in chunks))
        combined = "\n".join(chunks)
        self.assertIn("Всего пользователей: 120", combined)
        self.assertIn("Telegram ID: 100120", combined)


class AdminCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_admin_has_no_access(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=22),
            answer=AsyncMock(),
        )
        settings = Settings("token", "key", admin_ids=frozenset({11}))
        db = SimpleNamespace(get_admin_users=AsyncMock())

        await admin_users_command(message, db, settings)

        message.answer.assert_awaited_once_with(
            "⛔ У вас нет доступа к этой команде."
        )
        db.get_admin_users.assert_not_awaited()

    async def test_admin_sees_user_list(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=11),
            answer=AsyncMock(),
        )
        settings = Settings("token", "key", admin_ids=frozenset({11}))
        users = [
            make_admin_user(
                1,
                username="alice",
                full_name="Alice Admin",
                plan=PREMIUM,
            )
        ]
        db = SimpleNamespace(get_admin_users=AsyncMock(return_value=users))
        current_user = User(id=1, telegram_id=11, plan=PREMIUM)

        await admin_users_command(
            message,
            db,
            settings,
            profile_user=current_user,
        )

        message.answer.assert_awaited_once()
        text = message.answer.await_args.args[0]
        self.assertIn("Всего пользователей: 1", text)
        self.assertIn("Username: @alice", text)
        self.assertIn("Имя: Alice Admin", text)
        self.assertIn("Тариф: Premium", text)


class ProfileMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_any_regular_message_updates_profile(self) -> None:
        middleware = UserProfileMiddleware()
        handler = AsyncMock(return_value="ok")
        db = SimpleNamespace(
            upsert_user=AsyncMock(
                return_value=User(id=1, telegram_id=42, plan=FREE)
            )
        )
        event = SimpleNamespace(
            text="Привет",
            from_user=SimpleNamespace(
                id=42,
                is_bot=False,
                username="tester",
                first_name="Иван",
                last_name="Петров",
            ),
        )
        data = {"db": db}

        result = await middleware(handler, event, data)

        self.assertEqual(result, "ok")
        db.upsert_user.assert_awaited_once_with(
            42,
            "tester",
            "Иван",
            "Петров",
            "Иван Петров",
        )
        self.assertIn("profile_user", data)

    async def test_start_is_not_pre_registered(self) -> None:
        middleware = UserProfileMiddleware()
        handler = AsyncMock()
        db = SimpleNamespace(upsert_user=AsyncMock())
        event = SimpleNamespace(
            text="/start ref_123",
            from_user=SimpleNamespace(id=42, is_bot=False),
        )

        await middleware(handler, event, {"db": db})

        db.upsert_user.assert_not_awaited()
        handler.assert_awaited_once()

    async def test_start_payload_is_preserved_for_handler(self) -> None:
        middleware = UserProfileMiddleware()
        handler = AsyncMock(return_value="started")
        db = SimpleNamespace(upsert_user=AsyncMock())
        event = SimpleNamespace(
            text="/start@VoiceTextAIBot ref_123",
            from_user=SimpleNamespace(id=42, is_bot=False),
        )

        result = await middleware(handler, event, {"db": db})

        self.assertEqual(result, "started")
        db.upsert_user.assert_not_awaited()
        handler.assert_awaited_once_with(event, {"db": db})

    async def test_message_without_text_updates_profile(self) -> None:
        middleware = UserProfileMiddleware()
        handler = AsyncMock(return_value="voice-handled")
        db = SimpleNamespace(
            upsert_user=AsyncMock(
                return_value=User(id=1, telegram_id=42, plan=FREE)
            )
        )
        event = SimpleNamespace(
            text=None,
            from_user=SimpleNamespace(
                id=42,
                is_bot=False,
                username="voice_user",
                first_name="Voice",
                last_name="User",
            ),
        )

        result = await middleware(handler, event, {"db": db})

        self.assertEqual(result, "voice-handled")
        db.upsert_user.assert_awaited_once()
        handler.assert_awaited_once()

    async def test_whitespace_message_does_not_crash(self) -> None:
        middleware = UserProfileMiddleware()
        handler = AsyncMock(return_value="handled")
        db = SimpleNamespace(
            upsert_user=AsyncMock(
                return_value=User(id=1, telegram_id=42, plan=FREE)
            )
        )
        event = SimpleNamespace(
            text="   \n\t",
            from_user=SimpleNamespace(
                id=42,
                is_bot=False,
                username=None,
                first_name="Blank",
                last_name=None,
            ),
        )

        result = await middleware(handler, event, {"db": db})

        self.assertEqual(result, "handled")
        db.upsert_user.assert_awaited_once()
        handler.assert_awaited_once()


class AdminDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_columns_are_migrated_without_data_loss(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.db"
            async with aiosqlite.connect(path) as connection:
                await connection.execute(
                    """
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER NOT NULL UNIQUE,
                        is_premium INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                await connection.execute(
                    """
                    INSERT INTO users (
                        telegram_id,
                        is_premium,
                        created_at,
                        updated_at
                    )
                    VALUES (777, 0, '2026-01-01T00:00:00+00:00', 'now')
                    """
                )
                await connection.commit()

            db = Database(path)
            await db.initialize()
            await db.upsert_user(
                777,
                None,
                "Без",
                "Username",
                "Без Username",
            )
            users = await db.get_admin_users()

            self.assertEqual(len(users), 1)
            self.assertEqual(users[0].telegram_id, 777)
            self.assertIsNone(users[0].username)
            self.assertEqual(users[0].full_name, "Без Username")
            self.assertEqual(
                users[0].created_at,
                "2026-01-01T00:00:00+00:00",
            )

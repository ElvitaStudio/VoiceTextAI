import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import aiosqlite

from app.database import Database
from app.plans import FREE, PREMIUM, PRO


class DatabaseLimitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.db = Database(
            Path(self.temp_dir.name) / "test.db",
            daily_free_limit=5,
        )
        await self.db.initialize()
        self.user = await self.db.upsert_user(
            telegram_id=123,
            username="tester",
            first_name="Test",
        )

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_daily_limit_and_release(self) -> None:
        for expected_used in range(1, 6):
            reserved, used = await self.db.reserve_usage(self.user)
            self.assertTrue(reserved)
            self.assertEqual(used, expected_used)

        reserved, used = await self.db.reserve_usage(self.user)
        self.assertFalse(reserved)
        self.assertEqual(used, 5)

        await self.db.release_usage(self.user)
        reserved, used = await self.db.reserve_usage(self.user)
        self.assertTrue(reserved)
        self.assertEqual(used, 5)

    async def test_free_has_separate_ai_and_translation_limits(self) -> None:
        self.assertEqual(self.user.plan, FREE)
        self.assertTrue(await self.db.reserve_ai_action(self.user))
        self.assertFalse(await self.db.reserve_ai_action(self.user))
        self.assertTrue(await self.db.reserve_translation(self.user))
        self.assertFalse(await self.db.reserve_translation(self.user))

        usage = await self.db.get_ai_usage(self.user)
        self.assertEqual(usage.ai_actions_used, 1)
        self.assertEqual(usage.ai_actions_remaining, 0)
        self.assertEqual(usage.translations_used, 1)
        self.assertEqual(usage.translations_remaining, 0)

        await self.db.release_ai_action(self.user)
        await self.db.release_translation(self.user)
        self.assertTrue(await self.db.reserve_ai_action(self.user))
        self.assertTrue(await self.db.reserve_translation(self.user))

    async def test_free_ai_reservation_is_atomic(self) -> None:
        reservations = await asyncio.gather(
            self.db.reserve_ai_action(self.user),
            self.db.reserve_ai_action(self.user),
        )
        self.assertEqual(sorted(reservations), [False, True])

    async def test_translation_reservation_is_atomic(self) -> None:
        reservations = await asyncio.gather(
            self.db.reserve_translation(self.user),
            self.db.reserve_translation(self.user),
        )
        self.assertEqual(sorted(reservations), [False, True])

    async def test_pro_has_10_ai_and_5_translations(self) -> None:
        await self.db.set_user_plan(self.user.telegram_id, PRO)
        user = await self.db.upsert_user(123, "tester", "Test")
        self.assertEqual(user.plan, PRO)

        for _ in range(10):
            self.assertTrue(await self.db.reserve_ai_action(user))
        self.assertFalse(await self.db.reserve_ai_action(user))

        for _ in range(5):
            self.assertTrue(await self.db.reserve_translation(user))
        self.assertFalse(await self.db.reserve_translation(user))

        usage = await self.db.get_ai_usage(user)
        self.assertEqual(usage.ai_actions_used, 10)
        self.assertEqual(usage.ai_actions_remaining, 0)
        self.assertEqual(usage.translations_used, 5)
        self.assertEqual(usage.translations_remaining, 0)

    async def test_premium_has_limited_voice_and_unlimited_ai(self) -> None:
        await self.db.set_user_plan(self.user.telegram_id, PREMIUM)
        user = await self.db.upsert_user(123, "tester", "Test")
        voice_usage = await self.db.get_usage(user)
        ai_usage = await self.db.get_ai_usage(user)

        self.assertEqual(voice_usage.limit, 1000)
        self.assertIsNone(ai_usage.ai_actions_limit)
        self.assertIsNone(ai_usage.translations_limit)
        self.assertTrue(await self.db.reserve_ai_action(user))
        self.assertTrue(await self.db.reserve_translation(user))

        async with self.db._connect() as connection:
            await connection.execute(
                """
                INSERT INTO usage_limits (
                    user_id,
                    usage_date,
                    used_count,
                    updated_at
                )
                VALUES (?, ?, 999, 'now')
                ON CONFLICT(user_id, usage_date) DO UPDATE SET
                    used_count = 999
                """,
                (user.id, self.db._today()),
            )
            await connection.commit()

        reserved, used = await self.db.reserve_usage(user)
        self.assertTrue(reserved)
        self.assertEqual(used, 1000)
        reserved, used = await self.db.reserve_usage(user)
        self.assertFalse(reserved)
        self.assertEqual(used, 1000)

    async def test_usage_tables_are_separate(self) -> None:
        async with self.db._connect() as connection:
            cursor = await connection.execute(
                "PRAGMA table_info(ai_usage_limits)"
            )
            ai_columns = {row[1] for row in await cursor.fetchall()}
            cursor = await connection.execute(
                "PRAGMA table_info(translation_usage_limits)"
            )
            translation_columns = {
                row[1] for row in await cursor.fetchall()
            }

        self.assertIn("ai_actions_count", ai_columns)
        self.assertNotIn("translations_count", ai_columns)
        self.assertIn("translations_count", translation_columns)

    async def test_self_referral_is_rejected(self) -> None:
        result = await self.db.register_user(
            telegram_id=456,
            username="self_ref",
            first_name="Self",
            referred_by_telegram_id=456,
        )
        self.assertTrue(result.created)
        self.assertFalse(result.referral_rewarded)
        self.assertIsNone(result.user.referred_by)
        self.assertEqual(await self.db.get_referral_count(result.user.id), 0)

    async def test_referral_grants_premium_for_three_days(self) -> None:
        inviter = self.user
        before = datetime.now(UTC)
        result = await self.db.register_user(
            telegram_id=456,
            username="friend",
            first_name="Friend",
            referred_by_telegram_id=inviter.telegram_id,
            reward_days=3,
        )

        self.assertTrue(result.created)
        self.assertTrue(result.referral_rewarded)
        self.assertEqual(result.user.plan, FREE)
        self.assertEqual(result.user.referred_by, inviter.id)
        self.assertEqual(await self.db.get_referral_count(inviter.id), 1)

        rewarded_inviter = await self.db.upsert_user(
            inviter.telegram_id,
            "tester",
            "Test",
        )
        self.assertEqual(rewarded_inviter.plan, PREMIUM)
        premium_until = datetime.fromisoformat(
            rewarded_inviter.premium_until
        )
        self.assertGreaterEqual(
            premium_until,
            before + timedelta(days=3) - timedelta(seconds=2),
        )
        self.assertLess(
            premium_until,
            before + timedelta(days=3, minutes=1),
        )

    async def test_repeated_start_does_not_reward_twice(self) -> None:
        first = await self.db.register_user(
            telegram_id=456,
            username="friend",
            first_name="Friend",
            referred_by_telegram_id=self.user.telegram_id,
        )
        inviter_after_first = await self.db.upsert_user(
            self.user.telegram_id,
            "tester",
            "Test",
        )

        second = await self.db.register_user(
            telegram_id=456,
            username="friend",
            first_name="Friend",
            referred_by_telegram_id=self.user.telegram_id,
        )
        inviter_after_second = await self.db.upsert_user(
            self.user.telegram_id,
            "tester",
            "Test",
        )

        self.assertTrue(first.referral_rewarded)
        self.assertFalse(second.created)
        self.assertFalse(second.referral_rewarded)
        self.assertEqual(
            inviter_after_first.premium_until,
            inviter_after_second.premium_until,
        )
        self.assertEqual(await self.db.get_referral_count(self.user.id), 1)

    async def test_referral_columns_and_table_exist(self) -> None:
        async with self.db._connect() as connection:
            cursor = await connection.execute("PRAGMA table_info(users)")
            user_columns = {row[1] for row in await cursor.fetchall()}
            cursor = await connection.execute(
                "PRAGMA table_info(referrals)"
            )
            referral_columns = {row[1] for row in await cursor.fetchall()}

        self.assertIn("referred_by", user_columns)
        self.assertIn("premium_until", user_columns)
        self.assertEqual(
            referral_columns,
            {
                "id",
                "inviter_id",
                "invited_id",
                "reward_days",
                "created_at",
            },
        )

    async def test_existing_is_premium_user_is_migrated(self) -> None:
        async with self.db._connect() as connection:
            await connection.execute(
                """
                UPDATE users
                SET plan = 'free', is_premium = 1
                WHERE telegram_id = ?
                """,
                (self.user.telegram_id,),
            )
            await connection.commit()

        await self.db.initialize()
        migrated = await self.db.upsert_user(123, "tester", "Test")
        self.assertEqual(migrated.plan, PREMIUM)

    async def test_legacy_database_gets_plan_column(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        async with aiosqlite.connect(legacy_path) as connection:
            await connection.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT,
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
                    username,
                    first_name,
                    is_premium,
                    created_at,
                    updated_at
                )
                VALUES (777, 'legacy', 'Legacy', 1, 'now', 'now')
                """
            )
            await connection.commit()

        legacy_db = Database(legacy_path)
        await legacy_db.initialize()
        user = await legacy_db.upsert_user(777, "legacy", "Legacy")
        self.assertEqual(user.plan, PREMIUM)

    async def test_combined_ai_table_is_migrated(self) -> None:
        migration_path = Path(self.temp_dir.name) / "combined.db"
        migration_db = Database(migration_path)
        await migration_db.initialize()
        user = await migration_db.upsert_user(888, "old", "Old")

        async with migration_db._connect() as connection:
            await connection.execute("DROP TABLE ai_usage_limits")
            await connection.execute(
                """
                CREATE TABLE ai_usage_limits (
                    user_id INTEGER NOT NULL,
                    usage_date TEXT NOT NULL,
                    ai_actions_count INTEGER NOT NULL DEFAULT 0,
                    translations_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, usage_date)
                )
                """
            )
            await connection.execute(
                """
                INSERT INTO ai_usage_limits (
                    user_id,
                    usage_date,
                    ai_actions_count,
                    translations_count,
                    updated_at
                )
                VALUES (?, ?, 1, 1, 'now')
                """,
                (user.id, migration_db._today()),
            )
            await connection.commit()

        await migration_db.initialize()
        usage = await migration_db.get_ai_usage(user)
        self.assertEqual(usage.ai_actions_used, 1)
        self.assertEqual(usage.translations_used, 1)

        async with migration_db._connect() as connection:
            cursor = await connection.execute(
                "PRAGMA table_info(ai_usage_limits)"
            )
            columns = {row[1] for row in await cursor.fetchall()}
        self.assertNotIn("translations_count", columns)

    async def test_completed_message_is_available_only_to_owner(self) -> None:
        message_id = await self.db.create_message(
            user_id=self.user.id,
            telegram_message_id=42,
            telegram_file_id="file-id",
            duration_seconds=15,
        )
        await self.db.complete_message(
            message_id,
            raw_text="сырой текст",
            formatted_text="Готовый текст",
        )

        stored = await self.db.get_completed_message(message_id, self.user.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.formatted_text, "Готовый текст")

        stranger = await self.db.upsert_user(999, "stranger", "Stranger")
        forbidden = await self.db.get_completed_message(
            message_id,
            stranger.id,
        )
        self.assertIsNone(forbidden)

    async def test_history_limits_follow_plan(self) -> None:
        now = self.db._now()
        rows = [
            (
                self.user.id,
                1000 + index,
                f"file-{index}",
                10,
                f"raw-{index}",
                f"formatted-{index}",
                now,
                now,
            )
            for index in range(105)
        ]
        async with self.db._connect() as connection:
            await connection.executemany(
                """
                INSERT INTO messages (
                    user_id,
                    telegram_message_id,
                    telegram_file_id,
                    duration_seconds,
                    raw_text,
                    formatted_text,
                    status,
                    created_at,
                    completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?)
                """,
                rows,
            )
            await connection.commit()

        free_history = await self.db.get_message_history(self.user)
        self.assertEqual(len(free_history), 5)

        await self.db.set_user_plan(self.user.telegram_id, PRO)
        pro = await self.db.upsert_user(123, "tester", "Test")
        pro_history = await self.db.get_message_history(pro)
        self.assertEqual(len(pro_history), 30)

        await self.db.set_user_plan(self.user.telegram_id, PREMIUM)
        premium = await self.db.upsert_user(123, "tester", "Test")
        premium_history = await self.db.get_message_history(premium)
        self.assertEqual(len(premium_history), 100)

    async def test_history_contains_only_completed_messages(self) -> None:
        completed_id = await self.db.create_message(
            user_id=self.user.id,
            telegram_message_id=2001,
            telegram_file_id="completed",
            duration_seconds=10,
        )
        await self.db.complete_message(
            completed_id,
            raw_text="raw",
            formatted_text="completed text",
        )
        await self.db.create_message(
            user_id=self.user.id,
            telegram_message_id=2002,
            telegram_file_id="processing",
            duration_seconds=10,
        )

        history = await self.db.get_message_history(self.user)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].formatted_text, "completed text")

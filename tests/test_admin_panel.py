from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from app.admin import (
    admin_dashboard_text,
    admin_referral_chunks,
    admin_user_card_text,
)
from app.admin_keyboards import (
    admin_dashboard_keyboard,
    admin_user_card_keyboard,
    admin_users_keyboard,
)
from app.config import Settings
from app.database import (
    AdminReferral,
    AdminReferralReport,
    AdminStatistics,
    AdminUser,
    Database,
)
from app.handlers.admin import (
    ACCESS_DENIED,
    admin_callback,
    admin_command,
)
from app.plans import FREE, PREMIUM, PRO


def statistics() -> AdminStatistics:
    return AdminStatistics(
        total_users=15,
        free_users=10,
        pro_users=3,
        premium_users=2,
        users_today=4,
        voice_messages_total=30,
        ai_actions_today=7,
        translations_today=2,
    )


def panel_user(user_id: int = 1, plan: str = FREE) -> AdminUser:
    return AdminUser(
        user_id=user_id,
        telegram_id=1000 + user_id,
        username=f"user{user_id}",
        first_name="Иван",
        last_name="Петров",
        full_name="Иван Петров",
        plan=plan,
        premium_until=None,
        created_at="2026-06-19T10:00:00+00:00",
        voice_messages_used=8,
        ai_actions_today=2,
        translations_today=1,
        referrals_count=3,
    )


class AdminPanelPresentationTests(unittest.TestCase):
    def test_dashboard_contains_counts_and_actions(self) -> None:
        text = admin_dashboard_text(statistics())
        self.assertIn("👑 Панель администратора", text)
        self.assertIn("👥 Пользователей: 15", text)
        self.assertIn("⭐ Pro: 3", text)
        self.assertIn("👑 Premium: 2", text)

        buttons = [
            (button.text, button.callback_data)
            for row in admin_dashboard_keyboard().inline_keyboard
            for button in row
        ]
        self.assertEqual(
            buttons,
            [
                ("👥 Пользователи", "admin:users:0"),
                ("📊 Статистика", "admin:stats"),
                ("🎁 Рефералы", "admin:referrals"),
                ("⬅️ Закрыть", "admin:close"),
            ],
        )

    def test_user_card_contains_required_fields(self) -> None:
        text = admin_user_card_text(panel_user())
        self.assertIn("👤 Иван Петров", text)
        self.assertIn("🆔 Telegram ID: 1001", text)
        self.assertIn("📎 Username: @user1", text)
        self.assertIn("🎖 Тариф: Free", text)
        self.assertIn("🎙 Голосовых использовано: 8", text)
        self.assertIn("✨ AI-действий сегодня: 2", text)
        self.assertIn("🌍 Переводов сегодня: 1", text)
        self.assertIn("🎁 Пригласил пользователей: 3", text)

        callbacks = [
            button.callback_data
            for row in admin_user_card_keyboard(1, 2).inline_keyboard
            for button in row
        ]
        self.assertEqual(
            callbacks,
            [
                "admin:grant:extend:1:2",
                "admin:grant:premium:1:2",
                "admin:grant:pro:1:2",
                "admin:grant:free:1:2",
                "admin:users:2",
            ],
        )

    def test_long_referral_report_is_split(self) -> None:
        referrals = [
            AdminReferral(
                inviter_name="Пригласивший " + "А" * 50,
                inviter_username=f"inviter_{index}",
                invited_name="Приглашённый " + "Б" * 50,
                invited_username=f"invited_{index}",
                created_at="2026-06-19T10:00:00+00:00",
            )
            for index in range(100)
        ]
        chunks = admin_referral_chunks(
            AdminReferralReport(
                total_referrals=100,
                top_referrers=[],
                referrals=referrals,
            )
        )
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 4000 for chunk in chunks))


class AdminPanelHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_command_denies_non_admin(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=22),
            answer=AsyncMock(),
        )
        db = SimpleNamespace(get_admin_statistics=AsyncMock())
        settings = Settings("token", "key", admin_ids=frozenset({11}))

        await admin_command(message, db, settings)

        message.answer.assert_awaited_once_with(ACCESS_DENIED)
        db.get_admin_statistics.assert_not_awaited()

    async def test_admin_command_opens_dashboard(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=11),
            answer=AsyncMock(),
        )
        db = SimpleNamespace(
            get_admin_statistics=AsyncMock(return_value=statistics())
        )
        settings = Settings("token", "key", admin_ids=frozenset({11}))

        await admin_command(message, db, settings)

        message.answer.assert_awaited_once()
        args, kwargs = message.answer.await_args
        self.assertIn("👑 Панель администратора", args[0])
        self.assertEqual(kwargs["reply_markup"], admin_dashboard_keyboard())

    async def test_callback_denies_non_admin(self) -> None:
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=22),
            data="admin:stats",
            message=None,
            answer=AsyncMock(),
        )
        settings = Settings("token", "key", admin_ids=frozenset({11}))

        await admin_callback(callback, SimpleNamespace(), settings)

        callback.answer.assert_awaited_once_with(
            ACCESS_DENIED,
            show_alert=True,
        )

    async def test_grant_pro_action_refreshes_card(self) -> None:
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=11),
            data="admin:grant:pro:7:1",
            message=message,
            answer=AsyncMock(),
        )
        db = SimpleNamespace(
            set_admin_user_plan=AsyncMock(return_value=True),
            get_admin_user=AsyncMock(return_value=panel_user(7, PRO)),
        )
        settings = Settings("token", "key", admin_ids=frozenset({11}))

        with patch("app.handlers.admin.Message", SimpleNamespace):
            await admin_callback(callback, db, settings)

        db.set_admin_user_plan.assert_awaited_once_with(7, PRO)
        self.assertIn("🎖 Тариф: Pro", message.edit_text.await_args.args[0])
        callback.answer.assert_awaited_once_with("Тариф изменён на Pro")


class AdminPanelDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "admin.db")
        await self.db.initialize()

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_users_are_paginated_by_ten(self) -> None:
        for index in range(12):
            await self.db.upsert_user(
                10_000 + index,
                f"user{index}",
                "User",
                str(index),
                f"User {index}",
            )

        first_page = await self.db.get_admin_users_page(0)
        second_page = await self.db.get_admin_users_page(1)

        self.assertEqual(len(first_page.users), 10)
        self.assertEqual(len(second_page.users), 2)
        self.assertEqual(first_page.total_users, 12)
        self.assertEqual(first_page.total_pages, 2)
        buttons = admin_users_keyboard(first_page).inline_keyboard
        self.assertEqual(len(buttons[:10]), 10)
        self.assertIn(
            "➡️ Следующая",
            [button.text for button in buttons[10]],
        )

    async def test_plan_actions_and_temporary_premium(self) -> None:
        await self.db.upsert_user(
            500,
            "target",
            "Target",
            "User",
            "Target User",
        )
        target = (await self.db.get_admin_users_page(0)).users[0]

        self.assertTrue(
            await self.db.extend_admin_user_premium(target.user_id, 3)
        )
        extended = await self.db.get_admin_user(target.user_id)
        self.assertEqual(extended.plan, PREMIUM)
        self.assertGreater(
            datetime.fromisoformat(extended.premium_until),
            datetime.now(timezone.utc),
        )

        self.assertTrue(
            await self.db.set_admin_user_plan(target.user_id, PRO)
        )
        pro_user = await self.db.get_admin_user(target.user_id)
        self.assertEqual(pro_user.plan, PRO)
        self.assertIsNone(pro_user.premium_until)

        self.assertTrue(
            await self.db.set_admin_user_plan(target.user_id, PREMIUM)
        )
        premium_user = await self.db.get_admin_user(target.user_id)
        self.assertEqual(premium_user.plan, PREMIUM)

        self.assertTrue(
            await self.db.set_admin_user_plan(target.user_id, FREE)
        )
        free_user = await self.db.get_admin_user(target.user_id)
        self.assertEqual(free_user.plan, FREE)
        self.assertIsNone(free_user.premium_until)

    async def test_statistics_and_referral_report(self) -> None:
        inviter = await self.db.upsert_user(
            700,
            "inviter",
            "Invite",
            "Owner",
            "Invite Owner",
        )
        result = await self.db.register_user(
            telegram_id=701,
            username=None,
            first_name="New",
            last_name="User",
            full_name="New User",
            referred_by_telegram_id=inviter.telegram_id,
        )
        message_id = await self.db.create_message(
            inviter.id,
            1,
            "file",
            10,
        )
        await self.db.complete_message(message_id, "raw", "formatted")
        await self.db.reserve_ai_action(inviter)
        await self.db.reserve_translation(inviter)

        stats = await self.db.get_admin_statistics()
        report = await self.db.get_admin_referral_report()

        self.assertEqual(stats.total_users, 2)
        self.assertEqual(stats.voice_messages_total, 1)
        self.assertEqual(stats.ai_actions_today, 1)
        self.assertEqual(stats.translations_today, 1)
        self.assertTrue(result.referral_rewarded)
        self.assertEqual(report.total_referrals, 1)
        self.assertEqual(report.top_referrers[0].invited_count, 1)
        self.assertEqual(report.referrals[0].invited_name, "New User")

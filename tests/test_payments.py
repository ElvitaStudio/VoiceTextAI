from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.database import Database
from app.handlers.payments import (
    INVALID_PAYMENT_MESSAGE,
    build_payment_payload,
    payment_support,
    process_pre_checkout,
    process_successful_payment,
    send_plan_invoice,
)
from app.plans import PREMIUM, PRO


def callback_for(plan: str) -> SimpleNamespace:
    return SimpleNamespace(
        data=f"payment:{plan}",
        from_user=SimpleNamespace(id=12345),
        answer=AsyncMock(),
    )


def successful_message(
    plan: str,
    amount: int,
    charge_id: str,
) -> SimpleNamespace:
    user = SimpleNamespace(
        id=12345,
        username="buyer",
        first_name="Paying",
        last_name="User",
        full_name="Paying User",
    )
    return SimpleNamespace(
        from_user=user,
        successful_payment=SimpleNamespace(
            currency="XTR",
            total_amount=amount,
            invoice_payload=build_payment_payload(
                plan,
                user.id,
                timestamp=1_750_000_000,
            ),
            telegram_payment_charge_id=charge_id,
            provider_payment_charge_id="",
        ),
        answer=AsyncMock(),
    )


class InvoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_invoice_is_created_for_pro(self) -> None:
        callback = callback_for(PRO)
        bot = SimpleNamespace(send_invoice=AsyncMock())

        with patch("app.handlers.payments.time.time", return_value=1_750_000_000):
            await send_plan_invoice(callback, bot)

        kwargs = bot.send_invoice.await_args.kwargs
        self.assertEqual(kwargs["chat_id"], 12345)
        self.assertEqual(kwargs["title"], "VoiceText AI Pro")
        self.assertEqual(
            kwargs["description"],
            "Подписка VoiceText AI Pro на 30 дней",
        )
        self.assertEqual(
            kwargs["payload"],
            "plan:pro:12345:1750000000",
        )
        self.assertEqual(kwargs["currency"], "XTR")
        self.assertEqual(kwargs["provider_token"], "")
        self.assertEqual(kwargs["prices"][0].label, "Pro 30 days")
        self.assertEqual(kwargs["prices"][0].amount, 250)

    async def test_invoice_is_created_for_premium(self) -> None:
        callback = callback_for(PREMIUM)
        bot = SimpleNamespace(send_invoice=AsyncMock())

        with patch("app.handlers.payments.time.time", return_value=1_750_000_000):
            await send_plan_invoice(callback, bot)

        kwargs = bot.send_invoice.await_args.kwargs
        self.assertEqual(kwargs["title"], "VoiceText AI Premium")
        self.assertEqual(
            kwargs["description"],
            "Подписка VoiceText AI Premium на 30 дней",
        )
        self.assertEqual(
            kwargs["payload"],
            "plan:premium:12345:1750000000",
        )
        self.assertEqual(kwargs["prices"][0].label, "Premium 30 days")
        self.assertEqual(kwargs["prices"][0].amount, 500)


class PreCheckoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_pre_checkout_is_confirmed(self) -> None:
        query = SimpleNamespace(
            id="checkout-1",
            from_user=SimpleNamespace(id=12345),
            invoice_payload="plan:pro:12345:1750000000",
            currency="XTR",
            total_amount=250,
        )
        bot = SimpleNamespace(answer_pre_checkout_query=AsyncMock())

        await process_pre_checkout(query, bot)

        bot.answer_pre_checkout_query.assert_awaited_once_with(
            pre_checkout_query_id="checkout-1",
            ok=True,
        )

    async def test_invalid_pre_checkout_is_rejected(self) -> None:
        query = SimpleNamespace(
            id="checkout-2",
            from_user=SimpleNamespace(id=12345),
            invoice_payload="plan:premium:999:1750000000",
            currency="XTR",
            total_amount=500,
        )
        bot = SimpleNamespace(answer_pre_checkout_query=AsyncMock())

        await process_pre_checkout(query, bot)

        bot.answer_pre_checkout_query.assert_awaited_once_with(
            pre_checkout_query_id="checkout-2",
            ok=False,
            error_message=INVALID_PAYMENT_MESSAGE,
        )


class SuccessfulPaymentHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_payment_grants_pro(self) -> None:
        message = successful_message(PRO, 250, "charge-pro")
        db = SimpleNamespace(
            upsert_user=AsyncMock(),
            process_stars_payment=AsyncMock(return_value=True),
        )

        await process_successful_payment(message, db)

        kwargs = db.process_stars_payment.await_args.kwargs
        self.assertEqual(kwargs["plan"], PRO)
        self.assertEqual(kwargs["amount"], 250)
        self.assertEqual(kwargs["currency"], "XTR")
        self.assertEqual(kwargs["duration_days"], 30)
        self.assertEqual(kwargs["telegram_payment_charge_id"], "charge-pro")

    async def test_successful_payment_grants_premium(self) -> None:
        message = successful_message(PREMIUM, 500, "charge-premium")
        db = SimpleNamespace(
            upsert_user=AsyncMock(),
            process_stars_payment=AsyncMock(return_value=True),
        )

        await process_successful_payment(message, db)

        kwargs = db.process_stars_payment.await_args.kwargs
        self.assertEqual(kwargs["plan"], PREMIUM)
        self.assertEqual(kwargs["amount"], 500)
        message.answer.assert_awaited_once()

    async def test_paysupport_works(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())
        settings = Settings(
            "token",
            "key",
            support_username="VoiceTextSupport",
        )

        await payment_support(message, settings)

        text = message.answer.await_args.args[0]
        self.assertIn("💬 Поддержка по оплате", text)
        self.assertIn("@VoiceTextSupport", text)
        self.assertIn("• ваш Telegram ID", text)


class PaymentDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "payments.db")
        await self.db.initialize()
        self.user = await self.db.upsert_user(
            12345,
            "buyer",
            "Paying",
            "User",
            "Paying User",
        )

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_payment_is_saved_and_pro_is_granted(self) -> None:
        before = datetime.now(UTC)
        payload = "plan:pro:12345:1750000000"

        processed = await self.db.process_stars_payment(
            telegram_id=12345,
            plan=PRO,
            currency="XTR",
            amount=250,
            payload=payload,
            telegram_payment_charge_id="charge-pro-db",
            provider_payment_charge_id="",
        )

        self.assertTrue(processed)
        user = await self.db.upsert_user(
            12345,
            "buyer",
            "Paying",
            "User",
            "Paying User",
        )
        self.assertEqual(user.plan, PRO)
        self.assertGreaterEqual(
            datetime.fromisoformat(user.plan_until),
            before + timedelta(days=30) - timedelta(seconds=2),
        )
        payment = await self.db.get_payment_by_charge_id("charge-pro-db")
        self.assertIsNotNone(payment)
        self.assertEqual(payment.plan, PRO)
        self.assertEqual(payment.currency, "XTR")
        self.assertEqual(payment.amount, 250)
        self.assertEqual(payment.payload, payload)
        self.assertEqual(
            payment.telegram_payment_charge_id,
            "charge-pro-db",
        )

    async def test_premium_payment_sets_premium_until(self) -> None:
        processed = await self.db.process_stars_payment(
            telegram_id=12345,
            plan=PREMIUM,
            currency="XTR",
            amount=500,
            payload="plan:premium:12345:1750000000",
            telegram_payment_charge_id="charge-premium-db",
            provider_payment_charge_id="",
        )

        self.assertTrue(processed)
        user = await self.db.upsert_user(
            12345,
            "buyer",
            "Paying",
            "User",
            "Paying User",
        )
        self.assertEqual(user.plan, PREMIUM)
        self.assertEqual(user.premium_until, user.plan_until)

    async def test_duplicate_charge_does_not_extend_plan_twice(self) -> None:
        kwargs = {
            "telegram_id": 12345,
            "plan": PRO,
            "currency": "XTR",
            "amount": 250,
            "payload": "plan:pro:12345:1750000000",
            "telegram_payment_charge_id": "same-charge",
            "provider_payment_charge_id": "",
        }
        self.assertTrue(await self.db.process_stars_payment(**kwargs))
        first_user = await self.db.upsert_user(
            12345,
            "buyer",
            "Paying",
            "User",
            "Paying User",
        )

        self.assertFalse(await self.db.process_stars_payment(**kwargs))
        second_user = await self.db.upsert_user(
            12345,
            "buyer",
            "Paying",
            "User",
            "Paying User",
        )

        self.assertEqual(first_user.plan_until, second_user.plan_until)
        async with self.db._connect() as connection:
            cursor = await connection.execute(
                "SELECT COUNT(*) FROM payments"
            )
            count = (await cursor.fetchone())[0]
        self.assertEqual(count, 1)

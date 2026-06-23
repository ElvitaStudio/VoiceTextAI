from __future__ import annotations

from dataclasses import dataclass
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.config import Settings
from app.database import Database
from app.keyboards import PAYMENT_CALLBACK_PREFIX, referral_keyboard
from app.plans import PREMIUM, PRO
from app.referrals import build_referral_link, invite_message


router = Router(name="payments")
PAYMENT_CURRENCY = "XTR"
PAYMENT_DURATION_DAYS = 30
INVALID_PAYMENT_MESSAGE = "Некорректный платеж"


@dataclass(frozen=True, slots=True)
class PaymentPlan:
    plan: str
    title: str
    description: str
    label: str
    amount: int


PAYMENT_PLANS = {
    PRO: PaymentPlan(
        plan=PRO,
        title="VoiceText AI Pro",
        description="Подписка VoiceText AI Pro на 30 дней",
        label="Pro 30 days",
        amount=250,
    ),
    PREMIUM: PaymentPlan(
        plan=PREMIUM,
        title="VoiceText AI Premium",
        description="Подписка VoiceText AI Premium на 30 дней",
        label="Premium 30 days",
        amount=500,
    ),
}


def build_payment_payload(
    plan: str,
    user_id: int,
    timestamp: int | None = None,
) -> str:
    if plan not in PAYMENT_PLANS or user_id <= 0:
        raise ValueError("Invalid payment payload data")
    created_at = int(time.time()) if timestamp is None else timestamp
    if created_at <= 0:
        raise ValueError("Invalid payment timestamp")
    return f"plan:{plan}:{user_id}:{created_at}"


def parse_payment_payload(
    payload: str | None,
) -> tuple[str, int, int] | None:
    if not payload:
        return None
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "plan":
        return None
    plan = parts[1]
    try:
        user_id = int(parts[2])
        timestamp = int(parts[3])
    except ValueError:
        return None
    if plan not in PAYMENT_PLANS or user_id <= 0 or timestamp <= 0:
        return None
    return plan, user_id, timestamp


def _valid_payment(
    payload: str | None,
    telegram_user_id: int,
    currency: str,
    amount: int,
) -> tuple[str, int, int] | None:
    parsed = parse_payment_payload(payload)
    if parsed is None:
        return None
    plan, payload_user_id, timestamp = parsed
    payment_plan = PAYMENT_PLANS[plan]
    if (
        payload_user_id != telegram_user_id
        or currency != PAYMENT_CURRENCY
        or amount != payment_plan.amount
    ):
        return None
    return plan, payload_user_id, timestamp


@router.callback_query(
    F.data.in_(
        {
            f"{PAYMENT_CALLBACK_PREFIX}:{PRO}",
            f"{PAYMENT_CALLBACK_PREFIX}:{PREMIUM}",
        }
    )
)
async def send_plan_invoice(
    callback: CallbackQuery,
    bot: Bot,
) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer(INVALID_PAYMENT_MESSAGE, show_alert=True)
        return

    plan = callback.data.rsplit(":", 1)[-1]
    payment_plan = PAYMENT_PLANS.get(plan)
    if payment_plan is None:
        await callback.answer(INVALID_PAYMENT_MESSAGE, show_alert=True)
        return

    payload = build_payment_payload(plan, callback.from_user.id)
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=payment_plan.title,
        description=payment_plan.description,
        payload=payload,
        provider_token="",
        currency=PAYMENT_CURRENCY,
        prices=[
            LabeledPrice(
                label=payment_plan.label,
                amount=payment_plan.amount,
            )
        ],
    )
    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(
    pre_checkout_query: PreCheckoutQuery,
    bot: Bot,
) -> None:
    valid = _valid_payment(
        pre_checkout_query.invoice_payload,
        pre_checkout_query.from_user.id,
        pre_checkout_query.currency,
        pre_checkout_query.total_amount,
    )
    if valid is None:
        await bot.answer_pre_checkout_query(
            pre_checkout_query_id=pre_checkout_query.id,
            ok=False,
            error_message=INVALID_PAYMENT_MESSAGE,
        )
        return
    await bot.answer_pre_checkout_query(
        pre_checkout_query_id=pre_checkout_query.id,
        ok=True,
    )


@router.message(F.successful_payment)
async def process_successful_payment(
    message: Message,
    db: Database,
) -> None:
    payment = message.successful_payment
    if payment is None or message.from_user is None:
        return

    valid = _valid_payment(
        payment.invoice_payload,
        message.from_user.id,
        payment.currency,
        payment.total_amount,
    )
    if valid is None:
        await message.answer(
            "Платёж получен, но его данные не прошли проверку. "
            "Обратитесь в /paysupport."
        )
        return

    plan, _payload_user_id, _timestamp = valid
    await db.upsert_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        full_name=message.from_user.full_name,
    )
    processed = await db.process_stars_payment(
        telegram_id=message.from_user.id,
        plan=plan,
        currency=payment.currency,
        amount=payment.total_amount,
        payload=payment.invoice_payload,
        telegram_payment_charge_id=(
            payment.telegram_payment_charge_id
        ),
        provider_payment_charge_id=(
            payment.provider_payment_charge_id
        ),
        duration_days=PAYMENT_DURATION_DAYS,
    )
    if not processed:
        await message.answer("ℹ️ Этот платёж уже обработан.")
        return

    await message.answer(
        f"✅ Оплата прошла успешно!\n\n"
        f"Тариф {plan.title()} активирован на 30 дней."
    )


@router.message(Command("paysupport"))
async def payment_support(
    message: Message,
    settings: Settings,
) -> None:
    username = settings.support_username or "YOUR_SUPPORT_USERNAME"
    await message.answer(
        "💬 Поддержка по оплате\n\n"
        "Если у вас возникла проблема с оплатой, напишите нам:\n"
        f"@{username}\n\n"
        "Укажите:\n"
        "• ваш Telegram ID\n"
        "• тариф\n"
        "• дату оплаты"
    )


@router.callback_query(F.data == f"{PAYMENT_CALLBACK_PREFIX}:invite")
async def premium_invite_callback(
    callback: CallbackQuery,
    db: Database,
    bot_username: str,
) -> None:
    if callback.from_user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    await db.upsert_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        full_name=callback.from_user.full_name,
    )
    link = build_referral_link(bot_username, callback.from_user.id)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            invite_message(link),
            reply_markup=referral_keyboard(link),
        )
        await callback.answer()
        return
    await callback.answer("Сообщение недоступно", show_alert=True)

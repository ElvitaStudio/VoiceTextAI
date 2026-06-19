from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.database import Database
from app.keyboards import PAYMENT_CALLBACK_PREFIX
from app.referrals import build_referral_link, invite_message


router = Router(name="payments")


@router.callback_query(
    F.data.in_(
        {
            f"{PAYMENT_CALLBACK_PREFIX}:pro",
            f"{PAYMENT_CALLBACK_PREFIX}:premium",
        }
    )
)
async def payment_placeholder(callback: CallbackQuery) -> None:
    # TODO(v1.4): create Telegram Stars invoice and handle successful payment.
    await callback.answer(
        "Оплата Telegram Stars скоро появится.",
        show_alert=True,
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
        await callback.message.answer(invite_message(link))
        await callback.answer()
        return
    await callback.answer("Сообщение недоступно", show_alert=True)

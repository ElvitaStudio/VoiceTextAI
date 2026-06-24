from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.admin import (
    admin_dashboard_text,
    admin_referral_chunks,
    admin_statistics_text,
    admin_user_card_text,
    admin_users_page_text,
)
from app.admin_keyboards import (
    ADMIN_CALLBACK_PREFIX,
    BROADCAST_CALLBACK_PREFIX,
    admin_back_keyboard,
    admin_dashboard_keyboard,
    admin_user_card_keyboard,
    admin_users_keyboard,
    broadcast_confirm_keyboard,
)
from app.config import Settings
from app.database import BroadcastRecipient, Database, User
from app.plans import FREE, PREMIUM, PRO
from app.presentation import split_text


router = Router(name="admin")
ACCESS_DENIED = "⛔ У вас нет доступа."
BROADCAST_WAITING_TEXT = (
    "📣 Отправьте текст рассылки одним сообщением.\n\n"
    "Для отмены нажмите /cancel."
)
BROADCAST_CANCELLED = "❌ Рассылка отменена."
BROADCAST_RELEASE_TEXT = """🎉 Большое обновление VoiceText AI!

✨ Бесплатный лимит увеличен до 10 голосовых сообщений в сутки.

🌍 Добавлены новые языки перевода:

🇹🇷 Türkçe
🇵🇹 Português
🇦🇿 Azərbaycan
🇷🇴 Română
🇨🇿 Čeština
🇷🇸 Српски
🇳🇱 Nederlands

⚡ Улучшены AI-функции и работа бота.

🚀 Попробуйте новые возможности прямо сейчас!

Спасибо, что пользуетесь VoiceText AI ❤️"""
logger = logging.getLogger(__name__)


class BroadcastFlow(StatesGroup):
    waiting_text = State()
    waiting_confirm = State()


def _is_admin(user_id: int | None, settings: Settings) -> bool:
    return user_id is not None and user_id in settings.admin_ids


async def _edit_panel(
    message: Message,
    text: str,
    reply_markup,
) -> None:
    chunks = split_text(text)
    await message.edit_text(chunks[0], reply_markup=reply_markup)
    for chunk in chunks[1:]:
        await message.answer(chunk)


async def _show_dashboard(message: Message, db: Database) -> None:
    statistics = await db.get_admin_statistics()
    await _edit_panel(
        message,
        admin_dashboard_text(statistics),
        admin_dashboard_keyboard(),
    )


async def _show_users(
    message: Message,
    db: Database,
    page_number: int,
) -> None:
    page = await db.get_admin_users_page(page_number)
    await _edit_panel(
        message,
        admin_users_page_text(page),
        admin_users_keyboard(page),
    )


async def _show_user_card(
    message: Message,
    db: Database,
    user_id: int,
    page: int,
) -> bool:
    user = await db.get_admin_user(user_id)
    if user is None:
        return False
    await _edit_panel(
        message,
        admin_user_card_text(user),
        admin_user_card_keyboard(user_id, page),
    )
    return True


@router.message(Command("admin"))
async def admin_command(
    message: Message,
    db: Database,
    settings: Settings,
    profile_user: User | None = None,
) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not _is_admin(user_id, settings):
        await message.answer(ACCESS_DENIED)
        return

    statistics = await db.get_admin_statistics()
    await message.answer(
        admin_dashboard_text(statistics),
        reply_markup=admin_dashboard_keyboard(),
    )


@router.message(Command("broadcast"))
async def broadcast_command(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not _is_admin(user_id, settings):
        await message.answer(ACCESS_DENIED)
        return

    await state.clear()
    await state.set_state(BroadcastFlow.waiting_text)
    await message.answer(BROADCAST_WAITING_TEXT)


@router.message(Command("cancel"), BroadcastFlow.waiting_text)
@router.message(Command("cancel"), BroadcastFlow.waiting_confirm)
async def cancel_broadcast_command(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer(BROADCAST_CANCELLED)


@router.message(BroadcastFlow.waiting_text)
async def broadcast_text_received(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not _is_admin(user_id, settings):
        await state.clear()
        await message.answer(ACCESS_DENIED)
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Отправьте непустой текст рассылки.")
        return

    await state.update_data(text=text)
    await state.set_state(BroadcastFlow.waiting_confirm)
    await message.answer(
        f"📣 Предпросмотр рассылки:\n\n{text}",
        reply_markup=broadcast_confirm_keyboard(),
    )


def _is_blocked_error(error: Exception) -> bool:
    if isinstance(error, TelegramForbiddenError):
        return True
    if error.__class__.__name__ == "BotBlocked":
        return True
    message = str(error).lower()
    blocked_markers = (
        "forbidden",
        "blocked",
        "bot was blocked by the user",
        "user is deactivated",
        "chat not found",
        "bot can't initiate conversation",
    )
    return any(marker in message for marker in blocked_markers)


def _blocked_user_line(user: BroadcastRecipient) -> str:
    username = f" (@{user.username})" if user.username else ""
    return f"• {user.display_name}{username} — {user.telegram_id}"


def broadcast_report_chunks(
    *,
    total_users: int,
    sent: int,
    errors: int,
    blocked_users: list[BroadcastRecipient],
) -> list[str]:
    report = (
        "📢 Рассылка завершена.\n\n"
        f"Всего пользователей: {total_users}\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {errors}\n"
        f"Заблокировали бота: {len(blocked_users)}"
    )
    if blocked_users:
        blocked_lines = "\n".join(
            _blocked_user_line(user) for user in blocked_users
        )
        report += f"\n\n🚫 Заблокировали:\n\n{blocked_lines}"
    return split_text(report)


async def _send_broadcast(
    bot: Bot,
    db: Database,
    recipients: list[BroadcastRecipient],
    text: str,
) -> tuple[int, int, list[BroadcastRecipient]]:
    sent = 0
    errors = 0
    blocked_users: list[BroadcastRecipient] = []
    for recipient in recipients:
        try:
            await bot.send_message(recipient.telegram_id, text)
        except Exception as exc:  # pragma: no cover - logged and counted
            errors += 1
            if _is_blocked_error(exc):
                await db.mark_user_blocked(recipient.telegram_id)
                blocked_users.append(recipient)
            logger.warning(
                "Broadcast delivery failed: telegram_id=%s error=%s",
                recipient.telegram_id,
                exc,
            )
            continue
        sent += 1
    return sent, errors, blocked_users


@router.callback_query(
    F.data.startswith(f"{BROADCAST_CALLBACK_PREFIX}:"),
    BroadcastFlow.waiting_confirm,
)
async def broadcast_callback(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
    state: FSMContext,
    bot: Bot,
) -> None:
    user_id = callback.from_user.id if callback.from_user else None
    if not _is_admin(user_id, settings):
        await callback.answer(ACCESS_DENIED, show_alert=True)
        await state.clear()
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    action = (callback.data or "").split(":", maxsplit=1)[-1]
    if action == "cancel":
        await state.clear()
        await callback.message.answer(BROADCAST_CANCELLED)
        await callback.answer()
        return
    if action != "send":
        await callback.answer("Некорректная команда", show_alert=True)
        return

    data = await state.get_data()
    text = (data.get("text") or "").strip()
    if not text:
        await state.clear()
        await callback.answer("Текст рассылки не найден", show_alert=True)
        return

    recipients = await db.get_broadcast_recipients()
    sent, errors, blocked_users = await _send_broadcast(
        bot,
        db,
        recipients,
        text,
    )
    await state.clear()
    chunks = broadcast_report_chunks(
        total_users=len(recipients),
        sent=sent,
        errors=errors,
        blocked_users=blocked_users,
    )
    for chunk in chunks:
        await callback.message.answer(chunk)
    await callback.answer()


@router.callback_query(
    F.data.startswith(f"{ADMIN_CALLBACK_PREFIX}:")
)
async def admin_callback(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
) -> None:
    user_id = callback.from_user.id if callback.from_user else None
    if not _is_admin(user_id, settings):
        await callback.answer(ACCESS_DENIED, show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "home" and len(parts) == 2:
        await _show_dashboard(callback.message, db)
        await callback.answer()
        return

    if action == "close" and len(parts) == 2:
        await callback.message.delete()
        await callback.answer()
        return

    if action == "stats" and len(parts) == 2:
        statistics = await db.get_admin_statistics()
        await _edit_panel(
            callback.message,
            admin_statistics_text(statistics),
            admin_back_keyboard(),
        )
        await callback.answer()
        return

    if action == "referrals" and len(parts) == 2:
        report = await db.get_admin_referral_report()
        chunks = admin_referral_chunks(report)
        await callback.message.edit_text(
            chunks[0],
            reply_markup=admin_back_keyboard(),
        )
        for chunk in chunks[1:]:
            await callback.message.answer(chunk)
        await callback.answer()
        return

    if action == "users" and len(parts) == 3:
        try:
            page = int(parts[2])
        except ValueError:
            page = -1
        if page >= 0:
            await _show_users(callback.message, db, page)
            await callback.answer()
            return

    if action == "user" and len(parts) == 4:
        try:
            selected_user_id = int(parts[2])
            page = int(parts[3])
        except ValueError:
            selected_user_id = 0
            page = -1
        if selected_user_id > 0 and page >= 0:
            found = await _show_user_card(
                callback.message,
                db,
                selected_user_id,
                page,
            )
            if found:
                await callback.answer()
            else:
                await callback.answer(
                    "Пользователь не найден",
                    show_alert=True,
                )
            return

    if action == "grant" and len(parts) == 5:
        grant = parts[2]
        try:
            selected_user_id = int(parts[3])
            page = int(parts[4])
        except ValueError:
            selected_user_id = 0
            page = -1
        if selected_user_id > 0 and page >= 0:
            if grant == "extend":
                updated = await db.extend_admin_user_premium(
                    selected_user_id,
                    days=3,
                )
                notice = "Premium продлён на 3 дня"
            elif grant in {FREE, PRO, PREMIUM}:
                updated = await db.set_admin_user_plan(
                    selected_user_id,
                    grant,
                )
                notice = f"Тариф изменён на {grant.title()}"
            else:
                updated = False
                notice = ""

            if updated:
                await _show_user_card(
                    callback.message,
                    db,
                    selected_user_id,
                    page,
                )
                await callback.answer(notice)
            else:
                await callback.answer(
                    "Пользователь не найден",
                    show_alert=True,
                )
            return

    await callback.answer("Некорректная команда", show_alert=True)

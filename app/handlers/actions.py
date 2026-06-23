from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, Message

from app.database import Database
from app.keyboards import (
    CALLBACK_PREFIX,
    LANGUAGE_CALLBACK_PREFIX,
    text_actions_keyboard,
    translation_languages_keyboard,
)
from app.languages import SUPPORTED_LANGUAGES
from app.presentation import result_chunks, split_text
from app.services.openai_service import ACTION_INSTRUCTIONS, OpenAIService


router = Router(name="text_actions")
logger = logging.getLogger(__name__)
COPY_HEADER = "📋 Текст для копирования:"


def parse_callback_data(data: str | None) -> tuple[str, int] | None:
    if not data:
        return None

    parts = data.split(":")
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX:
        return None

    action = parts[1]
    try:
        message_id = int(parts[2])
    except ValueError:
        return None

    allowed_actions = {"copy", "translate", *ACTION_INSTRUCTIONS}
    if action not in allowed_actions or message_id <= 0:
        return None
    return action, message_id


def parse_language_callback(
    data: str | None,
) -> tuple[str, int] | None:
    if not data:
        return None

    parts = data.split(":")
    if len(parts) != 3 or parts[0] != LANGUAGE_CALLBACK_PREFIX:
        return None

    language_code = parts[1]
    try:
        message_id = int(parts[2])
    except ValueError:
        return None

    if (
        language_code not in {"back", *SUPPORTED_LANGUAGES}
        or message_id <= 0
    ):
        return None
    return language_code, message_id


async def send_result(
    target: Message,
    text: str,
    source_message_id: int,
) -> None:
    chunks = result_chunks(text)
    keyboard = text_actions_keyboard(source_message_id)

    if len(chunks) == 1:
        await target.edit_text(chunks[0], reply_markup=keyboard)
        return

    await target.edit_text(chunks[0])
    for chunk in chunks[1:-1]:
        await target.answer(chunk)
    await target.answer(chunks[-1], reply_markup=keyboard)


async def send_copyable_text(target: Message, text: str) -> None:
    await target.answer(COPY_HEADER)
    for chunk in split_text(text.strip()):
        await target.answer(chunk)


AI_LIMIT_MESSAGE = """🔒 Лимит AI-функций исчерпан.

⭐ Pro — 10 AI-функций в сутки.
👑 Premium — безлимитные AI-функции.

Подробнее: /premium"""

TRANSLATION_LIMIT_MESSAGE = """🌍 Лимит переводов исчерпан.

⭐ Pro — 5 переводов в сутки.
👑 Premium — безлимитный перевод.

Подробнее: /premium"""


@router.callback_query(F.data.startswith(f"{CALLBACK_PREFIX}:"))
async def handle_text_action(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    openai_service: OpenAIService,
) -> None:
    parsed = parse_callback_data(callback.data)
    if parsed is None or callback.from_user is None:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    action, message_id = parsed
    user = await db.upsert_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        full_name=callback.from_user.full_name,
    )
    stored_message = await db.get_completed_message(message_id, user.id)
    if stored_message is None:
        await callback.answer(
            "Текст не найден или больше недоступен",
            show_alert=True,
        )
        return

    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    if action == "copy":
        await callback.answer("Отправляю текст для копирования")
        await send_copyable_text(
            callback.message,
            stored_message.formatted_text,
        )
        return

    if action == "translate":
        await callback.message.edit_reply_markup(
            reply_markup=translation_languages_keyboard(stored_message.id)
        )
        await callback.answer("Выберите язык перевода")
        return

    reserved = await db.reserve_ai_action(user)
    if not reserved:
        await callback.answer(
            AI_LIMIT_MESSAGE,
            show_alert=True,
        )
        return

    generated = False
    status_message: Message | None = None
    try:
        await callback.answer("Обрабатываю…")
        await bot.send_chat_action(
            callback.message.chat.id,
            ChatAction.TYPING,
        )
        status_message = await callback.message.answer(
            "✨ Преобразую текст…"
        )
        result = await openai_service.transform_text(
            action,
            stored_message.formatted_text,
        )
        generated = True
        await send_result(status_message, result, stored_message.id)
    except Exception:
        logger.exception(
            "Failed text action %s for message %s and user %s",
            action,
            message_id,
            user.telegram_id,
        )
        if not generated:
            await db.release_ai_action(user)
        if status_message is not None:
            await status_message.edit_text(
                "Не удалось преобразовать текст. Попробуй ещё раз позже."
            )


@router.callback_query(
    F.data.startswith(f"{LANGUAGE_CALLBACK_PREFIX}:")
)
async def handle_translation_language(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    openai_service: OpenAIService,
) -> None:
    parsed = parse_language_callback(callback.data)
    if parsed is None or callback.from_user is None:
        await callback.answer("Некорректный язык", show_alert=True)
        return

    language_code, message_id = parsed
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    user = await db.upsert_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        full_name=callback.from_user.full_name,
    )
    stored_message = await db.get_completed_message(message_id, user.id)
    if stored_message is None:
        await callback.answer(
            "Текст не найден или больше недоступен",
            show_alert=True,
        )
        return

    if language_code == "back":
        await callback.message.edit_reply_markup(
            reply_markup=text_actions_keyboard(stored_message.id)
        )
        await callback.answer()
        return

    reserved = await db.reserve_translation(user)
    if not reserved:
        await callback.answer(
            TRANSLATION_LIMIT_MESSAGE,
            show_alert=True,
        )
        return

    language_button, _language_name = SUPPORTED_LANGUAGES[language_code]
    generated = False
    status_message: Message | None = None
    try:
        await callback.answer(f"Перевожу: {language_button}")
        await bot.send_chat_action(
            callback.message.chat.id,
            ChatAction.TYPING,
        )
        status_message = await callback.message.answer(
            "🌍 Перевожу текст…"
        )
        result = await openai_service.translate_text(
            language_code,
            stored_message.formatted_text,
        )
        generated = True
        await send_result(status_message, result, stored_message.id)
    except Exception:
        logger.exception(
            "Failed translation to %s for message %s and user %s",
            language_code,
            message_id,
            user.telegram_id,
        )
        if not generated:
            await db.release_translation(user)
        if status_message is not None:
            await status_message.edit_text(
                "Не удалось перевести текст. Попробуй ещё раз позже."
            )

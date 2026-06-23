from __future__ import annotations

from io import BytesIO
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from app.database import Database, User
from app.keyboards import text_actions_keyboard
from app.plans import format_duration, get_plan_limits
from app.presentation import result_chunks
from app.services.openai_service import OpenAIService


router = Router(name="voice")
logger = logging.getLogger(__name__)
async def get_user(
    message: Message,
    db: Database,
    profile_user: User | None = None,
) -> User:
    if profile_user is not None:
        return profile_user
    if message.from_user is None:
        raise ValueError("Message has no sender")
    return await db.upsert_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        full_name=message.from_user.full_name,
    )


@router.message(F.voice)
async def handle_voice(
    message: Message,
    bot: Bot,
    db: Database,
    openai_service: OpenAIService,
    profile_user: User | None = None,
) -> None:
    if message.voice is None:
        return

    user = await get_user(message, db, profile_user)
    duration = message.voice.duration
    plan_limits = get_plan_limits(user.effective_plan)

    if (
        not user.is_admin
        and
        plan_limits.max_voice_duration is not None
        and duration > plan_limits.max_voice_duration
    ):
        await message.answer(
            "⏱ Голосовое слишком длинное.\n"
            f"На тарифе {plan_limits.name} максимум — "
            f"{format_duration(plan_limits.max_voice_duration)}."
        )
        return

    reserved, _used = await db.reserve_usage(user)
    if not reserved:
        daily_limit = plan_limits.voice_daily_limit
        await message.answer(
            f"Лимит на сегодня исчерпан: "
            f"{daily_limit} из {daily_limit} голосовых.\n"
            "Новый лимит будет доступен завтра."
        )
        return

    db_message_id: int | None = None
    processing_completed = False
    status_message = await message.answer("⏳ Распознаю голосовое…")

    try:
        db_message_id = await db.create_message(
            user_id=user.id,
            telegram_message_id=message.message_id,
            telegram_file_id=message.voice.file_id,
            duration_seconds=duration,
        )

        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        telegram_file = await bot.get_file(message.voice.file_id)
        audio_buffer = BytesIO()
        await bot.download(telegram_file, destination=audio_buffer)
        audio = audio_buffer.getvalue()

        raw_text = await openai_service.transcribe(audio)
        await status_message.edit_text("✨ Привожу текст в порядок…")
        formatted_text = await openai_service.format_text(raw_text)

        await db.complete_message(db_message_id, raw_text, formatted_text)
        processing_completed = True
        chunks = result_chunks(formatted_text)
        keyboard = text_actions_keyboard(db_message_id)
        if len(chunks) == 1:
            await status_message.edit_text(chunks[0], reply_markup=keyboard)
        else:
            await status_message.edit_text(chunks[0])
            for chunk in chunks[1:-1]:
                await message.answer(chunk)
            await message.answer(chunks[-1], reply_markup=keyboard)
    except Exception as exc:
        logger.exception(
            "Failed to process voice message %s from user %s",
            message.message_id,
            user.telegram_id,
        )
        if db_message_id is not None and not processing_completed:
            await db.fail_message(db_message_id, str(exc))
        if not processing_completed:
            await db.release_usage(user)
            error_text = (
                "Не удалось обработать голосовое. Попробуй ещё раз позже — "
                "лимит за эту попытку не списан."
            )
        else:
            error_text = (
                "Текст обработан, но Telegram не смог доставить результат. "
                "Попробуй отправить голосовое ещё раз."
            )
        try:
            await status_message.edit_text(error_text)
        except Exception:
            logger.exception("Failed to send processing error to Telegram")


@router.message(F.audio | F.document)
async def unsupported_audio(message: Message) -> None:
    await message.answer(
        "Пока я принимаю только голосовые сообщения, записанные в Telegram."
    )


@router.message()
async def unsupported_message(message: Message) -> None:
    await message.answer(
        "Отправь голосовое сообщение, и я превращу его в аккуратный текст. "
        "Справка: /help"
    )

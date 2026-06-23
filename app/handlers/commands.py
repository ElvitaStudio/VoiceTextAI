import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message

from app.admin import admin_users_chunks
from app.config import Settings
from app.database import AIUsage, Database, Usage, User
from app.history import history_chunks
from app.keyboards import premium_keyboard, referral_keyboard
from app.middlewares import telegram_profile
from app.plans import FREE, PREMIUM, PRO, format_duration, get_plan_limits
from app.referrals import (
    REFERRAL_REWARD_DAYS,
    REFERRAL_COPY_CALLBACK,
    REFERRAL_COPY_HEADER,
    build_referral_link,
    invite_message,
    parse_referral_payload,
)


router = Router(name="commands")
logger = logging.getLogger(__name__)

REFERRAL_REWARD_NOTIFICATION = (
    "🎉 По вашей ссылке зарегистрировался новый пользователь!\n\n"
    "Вам начислен Premium на 3 дня.\n\n"
    "Проверить лимиты можно командой /limits."
)

PREMIUM_TEXT = """VoiceText AI v1.3.1

🆓 Free

• 5 голосовых в сутки
• До 2 минут
• 1 AI-функция в сутки
• 1 перевод в сутки
• Базовая обработка

⸻

⭐ Pro — $4.99/мес

• 100 голосовых в сутки
• До 10 минут
• 10 AI-функций в сутки
• 5 переводов в сутки
• История сообщений
• Приоритетная обработка

⸻

👑 Premium — $9.99/мес

• До 1000 голосовых в сутки
• До 30 минут
• Безлимитный перевод
• Безлимитные AI-функции
• История без ограничений
• Максимальный приоритет

🚀 Самая быстрая обработка
⭐ Premium badge
🎁 Ранний доступ к новым функциям"""


def _user_data(message: Message) -> tuple[
    int,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    return telegram_profile(message)


async def _current_user(
    message: Message,
    db: Database,
    profile_user: User | None,
) -> User:
    if profile_user is not None:
        return profile_user
    return await db.upsert_user(*_user_data(message))


def limits_text(
    user: User,
    voice_usage: Usage,
    ai_usage: AIUsage,
) -> str:
    limits = get_plan_limits(user.effective_plan)
    if user.is_admin:
        return (
            "📊 Ваш доступ: Администратор ⭐\n\n"
            "🎙 Голосовые: без ограничений\n"
            "⏳ Максимальная длина: без ограничений\n"
            "✨ AI-функции: без ограничений\n"
            "🌍 Переводы: без ограничений\n"
            "📚 История: без ограничений"
        )
    if user.effective_plan == PREMIUM:
        return (
            "📊 Ваш тариф: Premium ⭐\n\n"
            f"🎙 Использовано сегодня: "
            f"{voice_usage.used}/{voice_usage.limit}\n"
            "⏳ Максимальная длина голосового: 30 минут\n"
            f"Осталось голосовых: {voice_usage.remaining}\n\n"
            "✨ AI-функции: без ограничений\n"
            "🌍 Переводы: без ограничений"
        )

    base = (
        f"📊 Ваш тариф: {limits.name}\n\n"
        f"🎙 Использовано сегодня: "
        f"{voice_usage.used}/{voice_usage.limit}\n"
        f"⏳ Максимальная длина голосового: "
        f"{format_duration(limits.max_voice_duration)}\n"
        f"Осталось голосовых: {voice_usage.remaining}\n\n"
    )
    if user.effective_plan == FREE:
        return (
            base
            + f"✨ AI-функции сегодня: "
            f"{ai_usage.ai_actions_used}/"
            f"{ai_usage.ai_actions_limit}\n"
            f"Осталось AI-функций: "
            f"{ai_usage.ai_actions_remaining}\n"
            f"🌍 Переводы сегодня: "
            f"{ai_usage.translations_used}/"
            f"{ai_usage.translations_limit}\n"
            f"Осталось переводов: "
            f"{ai_usage.translations_remaining}"
        )
    if user.effective_plan == PRO:
        return (
            base
            + f"✨ AI-функции сегодня: "
            f"{ai_usage.ai_actions_used}/"
            f"{ai_usage.ai_actions_limit}\n"
            f"Осталось AI-функций: "
            f"{ai_usage.ai_actions_remaining}\n"
            f"🌍 Переводы сегодня: "
            f"{ai_usage.translations_used}/"
            f"{ai_usage.translations_limit}\n"
            f"Осталось переводов: "
            f"{ai_usage.translations_remaining}"
        )
    raise ValueError(f"Unsupported plan: {user.effective_plan}")


@router.message(CommandStart())
async def start_command(
    message: Message,
    command: CommandObject,
    db: Database,
    bot: Bot | None = None,
) -> None:
    telegram_id, username, first_name, last_name, full_name = _user_data(message)
    referred_by = parse_referral_payload(command.args)
    registration = await db.register_user(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        referred_by_telegram_id=referred_by,
        reward_days=REFERRAL_REWARD_DAYS,
    )
    if (
        registration.referral_rewarded
        and registration.rewarded_referrer_telegram_id is not None
    ):
        if bot is None:
            logger.warning(
                "Referral reward saved, but bot is unavailable: "
                "referrer=%s invitee=%s",
                registration.rewarded_referrer_telegram_id,
                telegram_id,
            )
        else:
            try:
                await bot.send_message(
                    registration.rewarded_referrer_telegram_id,
                    REFERRAL_REWARD_NOTIFICATION,
                )
            except Exception:
                logger.warning(
                    "Referral reward saved, but notification failed: "
                    "referrer=%s invitee=%s",
                    registration.rewarded_referrer_telegram_id,
                    telegram_id,
                    exc_info=True,
                )
    await message.answer(
        "👋 Привет! Я VoiceText AI.\n\n"
        "Отправь мне голосовое сообщение — я расшифрую его, "
        "исправлю пунктуацию и верну аккуратно оформленный текст.\n\n"
        "Бесплатный тариф: 5 голосовых в сутки, до 2 минут каждое.\n"
        "Также доступны 1 AI-функция и 1 перевод в сутки.\n"
        "Команда /help покажет подробности."
    )


@router.message(Command("help"))
async def help_command(
    message: Message,
    db: Database,
    profile_user: User | None = None,
) -> None:
    await _current_user(message, db, profile_user)
    await message.answer(
        "Как пользоваться:\n"
        "1. Запиши и отправь голосовое сообщение.\n"
        "2. Подожди, пока я распознаю и отредактирую текст.\n"
        "3. Скопируй готовый результат.\n\n"
        "Команды:\n"
        "/start — начать работу\n"
        "/help — помощь\n"
        "/limits — ваши тарифные лимиты\n"
        "/history — история сообщений\n"
        "/premium — тарифы VoiceText AI\n"
        "/paysupport — поддержка по оплате\n"
        "/invite — пригласить друга\n"
        "/admin — панель администратора\n"
        "/admin_users — список пользователей (для администраторов)"
    )


@router.message(Command("premium"))
async def premium_command(
    message: Message,
    db: Database,
    profile_user: User | None = None,
) -> None:
    await _current_user(message, db, profile_user)
    await message.answer(PREMIUM_TEXT, reply_markup=premium_keyboard())


@router.message(Command("invite"))
async def invite_command(
    message: Message,
    db: Database,
    bot_username: str,
    profile_user: User | None = None,
) -> None:
    user = await _current_user(message, db, profile_user)
    link = build_referral_link(bot_username, user.telegram_id)
    await message.answer(
        invite_message(link),
        reply_markup=referral_keyboard(link),
    )


@router.callback_query(F.data == REFERRAL_COPY_CALLBACK)
async def copy_referral_link(
    callback: CallbackQuery,
    db: Database,
    bot_username: str,
) -> None:
    if callback.from_user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    user = await db.upsert_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        full_name=callback.from_user.full_name,
    )
    if callback.message is None or not hasattr(callback.message, "answer"):
        await callback.answer("Сообщение недоступно", show_alert=True)
        return
    link = build_referral_link(bot_username, user.telegram_id)
    await callback.message.answer(
        f"{REFERRAL_COPY_HEADER}\n\n{link}"
    )
    await callback.answer()


@router.message(Command("limits"))
async def limits_command(
    message: Message,
    db: Database,
    profile_user: User | None = None,
) -> None:
    user = await _current_user(message, db, profile_user)
    voice_usage = await db.get_usage(user)
    ai_usage = await db.get_ai_usage(user)
    await message.answer(limits_text(user, voice_usage, ai_usage))


@router.message(Command("history"))
async def history_command(
    message: Message,
    db: Database,
    profile_user: User | None = None,
) -> None:
    user = await _current_user(message, db, profile_user)
    history = await db.get_message_history(user)
    for chunk in history_chunks(history):
        await message.answer(chunk)


@router.message(Command("admin_users"))
async def admin_users_command(
    message: Message,
    db: Database,
    settings: Settings,
    profile_user: User | None = None,
) -> None:
    if (
        message.from_user is None
        or message.from_user.id not in settings.admin_ids
    ):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return

    await _current_user(message, db, profile_user)
    users = await db.get_admin_users()
    for chunk in admin_users_chunks(users):
        await message.answer(chunk)

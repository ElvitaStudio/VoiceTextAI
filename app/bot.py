from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeChat

from app.config import load_settings
from app.config import Settings
from app.database import Database
from app.handlers import get_router
from app.services.openai_service import OpenAIService


USER_COMMANDS = [
    BotCommand(command="start", description="Начать работу"),
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="limits", description="Мои лимиты"),
    BotCommand(command="history", description="История сообщений"),
    BotCommand(command="premium", description="Premium"),
    BotCommand(command="paysupport", description="Помощь с оплатой"),
    BotCommand(command="invite", description="Пригласить друга"),
]
ADMIN_COMMANDS = [
    *USER_COMMANDS,
    BotCommand(command="admin", description="Админ-панель"),
    BotCommand(command="broadcast", description="Рассылка"),
]


async def set_commands(bot: Bot, settings: Settings) -> None:
    await bot.set_my_commands(USER_COMMANDS)
    for admin_id in settings.admin_ids:
        await bot.set_my_commands(
            ADMIN_COMMANDS,
            scope=BotCommandScopeChat(chat_id=admin_id),
        )


async def run_bot() -> None:
    settings = load_settings()
    db = Database(
        settings.database_path,
        admin_ids=settings.admin_ids,
    )
    await db.initialize()

    bot = Bot(token=settings.telegram_bot_token)
    bot_info = await bot.me()
    if not bot_info.username:
        await bot.session.close()
        raise RuntimeError("Telegram bot username is not configured")

    dispatcher = Dispatcher()
    dispatcher.include_router(get_router())

    openai_service = OpenAIService(
        api_key=settings.openai_api_key,
        transcription_model=settings.transcription_model,
        formatting_model=settings.formatting_model,
    )

    try:
        await set_commands(bot, settings)
        await dispatcher.start_polling(
            bot,
            db=db,
            settings=settings,
            openai_service=openai_service,
            bot_username=bot_info.username,
        )
    finally:
        await bot.session.close()

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.languages import SUPPORTED_LANGUAGES


CALLBACK_PREFIX = "text"
LANGUAGE_CALLBACK_PREFIX = "lang"
PAYMENT_CALLBACK_PREFIX = "payment"


def text_actions_keyboard(message_id: int) -> InlineKeyboardMarkup:
    def button(text: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text,
            callback_data=f"{CALLBACK_PREFIX}:{action}:{message_id}",
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button("📋 Копировать", "copy")],
            [
                button("✨ Улучшить", "improve"),
                button("💼 Деловой стиль", "business"),
            ],
            [
                button("📝 Кратко", "summary"),
                button("🌍 Перевести", "translate"),
            ],
            [button("📢 Пост для Telegram", "telegram_post")],
            [
                button("📧 Email", "email"),
                button("📋 Список задач", "tasks"),
            ],
        ]
    )


def translation_languages_keyboard(message_id: int) -> InlineKeyboardMarkup:
    language_buttons = [
        InlineKeyboardButton(
            text=button_text,
            callback_data=(
                f"{LANGUAGE_CALLBACK_PREFIX}:{code}:{message_id}"
            ),
        )
        for code, (button_text, _language_name) in SUPPORTED_LANGUAGES.items()
    ]
    rows = [
        language_buttons[index:index + 2]
        for index in range(0, len(language_buttons), 2)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=(
                    f"{LANGUAGE_CALLBACK_PREFIX}:back:{message_id}"
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Купить Pro",
                    callback_data=f"{PAYMENT_CALLBACK_PREFIX}:pro",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👑 Купить Premium",
                    callback_data=f"{PAYMENT_CALLBACK_PREFIX}:premium",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎁 Пригласить друга",
                    callback_data=f"{PAYMENT_CALLBACK_PREFIX}:invite",
                )
            ],
        ]
    )

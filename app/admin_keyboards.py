from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.admin import admin_user_button_text
from app.database import AdminUserPage


ADMIN_CALLBACK_PREFIX = "admin"


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=f"{ADMIN_CALLBACK_PREFIX}:{data}",
    )


def admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("👥 Пользователи", "users:0")],
            [_button("📊 Статистика", "stats")],
            [_button("🎁 Рефералы", "referrals")],
            [_button("⬅️ Закрыть", "close")],
        ]
    )


def admin_users_keyboard(page: AdminUserPage) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(
                admin_user_button_text(
                    page.page * 10 + index,
                    user,
                ),
                f"user:{user.user_id}:{page.page}",
            )
        ]
        for index, user in enumerate(page.users, start=1)
    ]
    navigation: list[InlineKeyboardButton] = []
    if page.page > 0:
        navigation.append(
            _button("◀️ Предыдущая", f"users:{page.page - 1}")
        )
    if page.page + 1 < page.total_pages:
        navigation.append(
            _button("➡️ Следующая", f"users:{page.page + 1}")
        )
    if navigation:
        rows.append(navigation)
    rows.append([_button("⬅️ Назад", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_card_keyboard(
    user_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    suffix = f"{user_id}:{page}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("🎁 +3 дня Premium", f"grant:extend:{suffix}")],
            [_button("👑 Выдать Premium", f"grant:premium:{suffix}")],
            [_button("⭐ Выдать Pro", f"grant:pro:{suffix}")],
            [_button("🆓 Сбросить Free", f"grant:free:{suffix}")],
            [_button("⬅️ Назад к списку", f"users:{page}")],
        ]
    )


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button("⬅️ Назад", "home")]]
    )

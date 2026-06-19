from __future__ import annotations

from datetime import datetime

from app.database import (
    AdminReferralReport,
    AdminStatistics,
    AdminUser,
    AdminUserPage,
)


TELEGRAM_MESSAGE_LIMIT = 4096
SAFE_MESSAGE_LIMIT = 4000


def _format_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%d.%m.%Y %H:%M")


def _format_user(index: int, user: AdminUser) -> str:
    lines = [
        f"{index}. Telegram ID: {user.telegram_id}",
    ]
    if user.username:
        lines.append(f"Username: @{user.username}")
    lines.extend(
        [
            f"Имя: {user.display_name}",
            f"Тариф: {user.plan.title()}",
        ]
    )
    premium_until = _format_datetime(user.premium_until)
    if premium_until:
        lines.append(f"Premium до: {premium_until}")
    created_at = _format_datetime(user.created_at)
    if created_at:
        lines.append(f"Регистрация: {created_at}")
    return "\n".join(lines)


def admin_users_chunks(
    users: list[AdminUser],
    limit: int = SAFE_MESSAGE_LIMIT,
) -> list[str]:
    if limit > TELEGRAM_MESSAGE_LIMIT:
        raise ValueError("Telegram message limit cannot exceed 4096")

    header = f"👥 Пользователи\n\nВсего пользователей: {len(users)}"
    if not users:
        return [header]

    continuation = "👥 Пользователи — продолжение"
    chunks: list[str] = []
    current = header
    for index, user in enumerate(users, start=1):
        entry = _format_user(index, user)
        candidate = f"{current}\n\n{entry}"
        if len(candidate) <= limit:
            current = candidate
            continue
        chunks.append(current)
        current = f"{continuation}\n\n{entry}"
    chunks.append(current)
    return chunks


def admin_dashboard_text(statistics: AdminStatistics) -> str:
    return (
        "👑 Панель администратора\n\n"
        f"👥 Пользователей: {statistics.total_users}\n"
        f"⭐ Pro: {statistics.pro_users}\n"
        f"👑 Premium: {statistics.premium_users}\n\n"
        "Выберите действие:"
    )


def admin_users_page_text(page: AdminUserPage) -> str:
    return (
        "👥 Пользователи\n\n"
        f"Всего: {page.total_users}\n"
        f"Страница: {page.page + 1}/{page.total_pages}\n\n"
        "Выберите пользователя:"
    )


def admin_user_button_text(index: int, user: AdminUser) -> str:
    label = f"{index}. {user.display_name}"
    if user.username:
        label += f" / @{user.username}"
    return label[:64]


def admin_user_card_text(user: AdminUser) -> str:
    username = f"@{user.username}" if user.username else "—"
    premium_until = _format_datetime(user.premium_until) or "—"
    created_at = _format_datetime(user.created_at) or "—"
    return (
        f"👤 {user.display_name}\n"
        f"🆔 Telegram ID: {user.telegram_id}\n"
        f"📎 Username: {username}\n"
        f"🎖 Тариф: {user.plan.title()}\n"
        f"⏳ Premium until: {premium_until}\n"
        f"📅 Регистрация: {created_at}\n"
        f"🎙 Голосовых использовано: {user.voice_messages_used}\n"
        f"✨ AI-действий сегодня: {user.ai_actions_today}\n"
        f"🌍 Переводов сегодня: {user.translations_today}\n"
        f"🎁 Пригласил пользователей: {user.referrals_count}"
    )


def admin_statistics_text(statistics: AdminStatistics) -> str:
    return (
        "📊 Статистика\n\n"
        f"👥 Всего пользователей: {statistics.total_users}\n"
        f"🆓 Free: {statistics.free_users}\n"
        f"⭐ Pro: {statistics.pro_users}\n"
        f"👑 Premium: {statistics.premium_users}\n"
        f"🆕 Пользователей за сегодня: {statistics.users_today}\n"
        f"🎙 Обработано голосовых всего: "
        f"{statistics.voice_messages_total}\n"
        f"✨ AI-действий сегодня: {statistics.ai_actions_today}\n"
        f"🌍 Переводов сегодня: {statistics.translations_today}"
    )


def _referral_name(name: str, username: str | None) -> str:
    if username:
        return f"{name} (@{username})"
    return name


def admin_referral_chunks(
    report: AdminReferralReport,
    limit: int = SAFE_MESSAGE_LIMIT,
) -> list[str]:
    blocks = [
        "🎁 Рефералы",
        f"Всего приглашений: {report.total_referrals}",
    ]
    if report.top_referrers:
        top_lines = ["🏆 Топ пригласителей:"]
        for index, referrer in enumerate(report.top_referrers, start=1):
            name = _referral_name(
                referrer.display_name,
                referrer.username,
            )
            top_lines.append(
                f"{index}. {name} — {referrer.invited_count}"
            )
        blocks.append("\n".join(top_lines))
    else:
        blocks.append("🏆 Топ пригласителей: пока пусто")

    if report.referrals:
        blocks.append("🔗 Кто кого пригласил:")
        for referral in report.referrals:
            inviter = _referral_name(
                referral.inviter_name,
                referral.inviter_username,
            )
            invited = _referral_name(
                referral.invited_name,
                referral.invited_username,
            )
            created_at = _format_datetime(referral.created_at) or "—"
            blocks.append(f"{inviter} → {invited}\n📅 {created_at}")
    else:
        blocks.append("🔗 Приглашений пока нет.")

    chunks: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = block
    if current:
        chunks.append(current)
    return chunks

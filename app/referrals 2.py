REFERRAL_REWARD_DAYS = 3


def build_referral_link(bot_username: str, user_id: int) -> str:
    username = bot_username.lstrip("@")
    return f"https://t.me/{username}?start=ref_{user_id}"


def parse_referral_payload(payload: str | None) -> int | None:
    if not payload or not payload.startswith("ref_"):
        return None

    raw_user_id = payload.removeprefix("ref_")
    try:
        user_id = int(raw_user_id)
    except ValueError:
        return None
    return user_id if user_id > 0 else None


def invite_message(referral_link: str) -> str:
    return (
        "🎁 Пригласите друга и получите Premium на 3 дня!\n\n"
        "Ваша ссылка:\n\n"
        f"{referral_link}\n\n"
        "Условия:\n\n"
        "• друг должен впервые запустить бота по вашей ссылке;\n"
        "• после нажатия /start вы получите Premium на 3 дня;\n"
        "• награда начисляется только один раз за каждого нового "
        "пользователя."
    )

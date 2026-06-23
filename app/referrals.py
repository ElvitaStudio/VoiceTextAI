from urllib.parse import quote, urlencode


REFERRAL_REWARD_DAYS = 3
REFERRAL_COPY_CALLBACK = "referral:copy"
REFERRAL_COPY_HEADER = "📋 Ваша ссылка для копирования:"
RU_INVITE_SHARE_TEXT = (
    "🎙 Попробуй VoiceText AI — бот расшифровывает голосовые сообщения, "
    "исправляет пунктуацию и помогает оформить текст.\n\n"
    "По моей ссылке ты можешь запустить бота:"
)
EN_INVITE_SHARE_TEXT = (
    "🎙 Try VoiceText AI — it transcribes voice messages, fixes punctuation "
    "and helps format text.\n\n"
    "Start the bot using my link:"
)


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


def build_referral_share_url(
    referral_link: str,
    language: str = "ru",
) -> str:
    invite_text = (
        EN_INVITE_SHARE_TEXT
        if language == "en"
        else RU_INVITE_SHARE_TEXT
    )
    return "https://t.me/share/url?" + urlencode(
        {
            "url": referral_link,
            "text": invite_text,
        },
        quote_via=quote,
    )


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

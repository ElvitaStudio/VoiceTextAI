from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    database_path: Path = BASE_DIR / "data" / "voicetext.db"
    transcription_model: str = "gpt-4o-mini-transcribe"
    formatting_model: str = "gpt-5.5"
    admin_ids: frozenset[int] = frozenset()
    support_username: str = ""


def parse_admin_ids(value: str) -> frozenset[int]:
    admin_ids: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            admin_id = int(item)
        except ValueError as exc:
            raise RuntimeError(
                f"ADMIN_IDS contains an invalid Telegram ID: {item}"
            ) from exc
        if admin_id <= 0:
            raise RuntimeError("ADMIN_IDS must contain positive integers")
        admin_ids.add(admin_id)
    return frozenset(admin_ids)


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    missing = []
    if not telegram_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not openai_key:
        missing.append("OPENAI_API_KEY")
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variables: {names}")

    return Settings(
        telegram_bot_token=telegram_token,
        openai_api_key=openai_key,
        admin_ids=parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        support_username=os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@"),
    )

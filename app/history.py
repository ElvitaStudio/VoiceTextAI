from datetime import datetime, timezone

from app.database import HistoryMessage


HISTORY_HEADER = "📜 История сообщений"
EMPTY_HISTORY_TEXT = (
    "📭 История пока пустая. Отправьте голосовое сообщение."
)
TELEGRAM_TEXT_LIMIT = 4096
HISTORY_FRAGMENT_LIMIT = 300


def history_fragment(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= HISTORY_FRAGMENT_LIMIT:
        return compact
    return compact[: HISTORY_FRAGMENT_LIMIT - 3].rstrip() + "..."


def format_history_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%d.%m.%Y %H:%M")


def history_chunks(
    history: list[HistoryMessage],
    limit: int = TELEGRAM_TEXT_LIMIT,
) -> list[str]:
    if not history:
        return [EMPTY_HISTORY_TEXT]

    entries = [
        (
            f"{index}. {format_history_datetime(item.created_at)}\n"
            f"📝 {history_fragment(item.formatted_text)}"
        )
        for index, item in enumerate(history, start=1)
    ]

    chunks: list[str] = []
    current = HISTORY_HEADER
    for entry in entries:
        candidate = f"{current}\n\n{entry}"
        if len(candidate) <= limit:
            current = candidate
            continue
        chunks.append(current)
        current = entry
    chunks.append(current)
    return chunks

RESULT_HEADER = "📝 Готовый текст"
RESULT_FOOTER = "━━━━━━━━━━━━\n✨ VoiceText AI"
TELEGRAM_TEXT_LIMIT = 4096


def split_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break

        split_at = rest.rfind("\n", 0, limit + 1)
        if split_at < limit // 2:
            split_at = rest.rfind(" ", 0, limit + 1)
        if split_at < limit // 2:
            split_at = limit

        chunk = rest[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        rest = rest[split_at:].strip()
    return chunks


def render_result(text: str) -> str:
    return f"{RESULT_HEADER}\n\n{text.strip()}\n\n{RESULT_FOOTER}"


def result_chunks(
    text: str,
    limit: int = TELEGRAM_TEXT_LIMIT,
) -> list[str]:
    clean_text = text.strip()
    complete_result = render_result(clean_text)
    if len(complete_result) <= limit:
        return [complete_result]

    max_decoration_length = max(
        len(RESULT_HEADER) + 2,
        len(RESULT_FOOTER) + 2,
    )
    body_limit = limit - max_decoration_length
    body_chunks = split_text(clean_text, body_limit)
    rendered: list[str] = []

    for index, chunk in enumerate(body_chunks):
        content = chunk
        if index == 0:
            content = f"{RESULT_HEADER}\n\n{content}"
        if index == len(body_chunks) - 1:
            content = f"{content}\n\n{RESULT_FOOTER}"
        rendered.append(content)

    return rendered

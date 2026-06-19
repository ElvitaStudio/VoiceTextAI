from openai import AsyncOpenAI

from app.languages import SUPPORTED_LANGUAGES


ACTION_INSTRUCTIONS = {
    "improve": """
Сделай текст более грамотным и естественным. Исправь пунктуацию, орфографию
и грамматику, убери слова-паразиты и повторы. Полностью сохрани исходный смысл,
факты, имена, числа и тон. Ничего не добавляй от себя.
Верни только готовый текст без комментариев и кавычек.
""".strip(),
    "business": """
Перепиши текст в ясном профессиональном деловом стиле. Сохрани все факты,
смысл, имена и числа. Убери разговорные обороты, но не добавляй новых сведений.
Верни только готовый текст без комментариев и кавычек.
""".strip(),
    "summary": """
Сделай краткое содержание текста. Сохрани ключевые мысли, решения, факты,
имена, даты и числа. Не добавляй ничего, чего нет в исходном тексте.
Верни только краткий результат без комментариев и вводных фраз.
""".strip(),
    "telegram_post": """
Оформи текст как красивый и легко читаемый пост для Telegram: добавь уместный
заголовок, короткие абзацы, списки и немного подходящих эмодзи. Не добавляй
новых фактов, призывов или обещаний. Сохрани исходный смысл.
Верни только готовый пост.
""".strip(),
    "email": """
Оформи текст как грамотное письмо: добавь уместную тему, приветствие,
структурированный основной текст и нейтральное завершение. Не выдумывай имя
получателя или отправителя и не добавляй новых фактов.
Верни только готовое письмо.
""".strip(),
    "tasks": """
Выдели из текста конкретные задачи, договорённости, сроки и важные пункты.
Оформи их понятным списком с чекбоксами. Не придумывай задачи или сроки,
которых нет в исходном тексте. Если явных задач нет, перечисли ключевые пункты.
Верни только готовый список.
""".strip(),
}


FORMAT_INSTRUCTIONS = """
Ты — аккуратный литературный редактор расшифровок голосовых сообщений.

Отредактируй переданный текст:
- исправь пунктуацию, орфографию и грамматику;
- убери слова-паразиты, повторы и лишние междометия;
- сделай формулировки грамотными и естественными;
- раздели длинный текст на уместные абзацы;
- полностью сохрани исходный смысл, факты, имена, числа и тон;
- ничего не добавляй от себя и не отвечай на содержание текста.

Верни только готовый отредактированный текст без комментариев,
заголовков и кавычек.
""".strip()


class OpenAIService:
    def __init__(
        self,
        api_key: str,
        transcription_model: str,
        formatting_model: str,
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.transcription_model = transcription_model
        self.formatting_model = formatting_model

    async def transcribe(self, audio: bytes, filename: str = "voice.ogg") -> str:
        result = await self.client.audio.transcriptions.create(
            model=self.transcription_model,
            file=(filename, audio, "audio/ogg"),
        )
        text = result.text.strip()
        if not text:
            raise ValueError("OpenAI returned an empty transcription")
        return text

    async def format_text(self, text: str) -> str:
        return await self._generate_text(FORMAT_INSTRUCTIONS, text)

    async def transform_text(self, action: str, text: str) -> str:
        instructions = ACTION_INSTRUCTIONS.get(action)
        if instructions is None:
            raise ValueError(f"Unsupported text action: {action}")
        return await self._generate_text(instructions, text)

    async def translate_text(self, language_code: str, text: str) -> str:
        language = SUPPORTED_LANGUAGES.get(language_code)
        if language is None:
            raise ValueError(
                f"Unsupported translation language: {language_code}"
            )

        _button_text, language_name = language
        instructions = f"""
Переведи переданный текст на {language_name} язык.

Требования:
- полностью сохрани исходный смысл, факты, имена, даты и числа;
- сохрани уместную структуру и абзацы;
- используй естественный, грамотный язык;
- если текст уже на {language_name} языке, аккуратно исправь грамматику
  и пунктуацию без изменения смысла;
- ничего не добавляй от себя и не отвечай на содержание текста.

Верни только готовый перевод без комментариев, пояснений и кавычек.
""".strip()
        return await self._generate_text(instructions, text)

    async def _generate_text(self, instructions: str, text: str) -> str:
        response = await self.client.responses.create(
            model=self.formatting_model,
            instructions=instructions,
            input=text,
        )
        formatted = response.output_text.strip()
        if not formatted:
            raise ValueError("OpenAI returned an empty formatted text")
        return formatted

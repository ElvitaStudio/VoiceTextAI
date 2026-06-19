# VoiceText AI 🎙️

Transform Telegram voice messages into polished, structured text with AI.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?logo=telegram&logoColor=white)](https://docs.aiogram.dev/)
[![OpenAI](https://img.shields.io/badge/OpenAI-API-412991?logo=openai&logoColor=white)](https://platform.openai.com/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

VoiceText AI is a Telegram bot that transcribes voice messages with OpenAI
Speech-to-Text, fixes punctuation, removes filler words and returns clean text
without changing its meaning.

Current release: **v1.4**

## Features

- Telegram voice-message transcription
- AI-powered punctuation and grammar cleanup
- Text improvement and business style
- Summaries and task extraction
- Translation into multiple languages
- Telegram post and email generation
- Inline actions for processed text
- Message history based on the active plan
- Daily voice, AI-action and translation limits
- Free, Pro and Premium plans
- Referral rewards with temporary Premium access
- Inline admin panel with statistics and user management
- Automatic SQLite schema migrations

## Plans

| Plan | Voice messages | Maximum duration | AI functions | Translations |
| --- | ---: | ---: | ---: | ---: |
| Free | 5/day | 2 minutes | 1/day | 1/day |
| Pro — $4.99/month | 100/day | 10 minutes | 10/day | 5/day |
| Premium — $9.99/month | 1000/day | 30 minutes | Unlimited | Unlimited |

Premium also includes unlimited history, maximum processing priority and
early access to new features.

> Payment buttons are currently placeholders. Telegram Stars payments are
> planned for a future release.

## Referral system

The `/invite` command creates a personal referral link:

```text
https://t.me/<bot_username>?start=ref_<user_id>
```

When a new user starts the bot through the link:

- the inviter receives Premium for 3 days;
- the invited user remains on the Free plan;
- self-referrals are rejected;
- each invited user can trigger the reward only once.

## Admin panel

Administrators listed in `ADMIN_IDS` can open the panel with `/admin`.

The inline panel provides:

- paginated user list;
- detailed user and usage cards;
- Free, Pro and Premium plan management;
- temporary Premium extension for 3 days;
- user, voice, AI-action and translation statistics;
- referral totals, top inviters and referral history.

Every admin callback validates access again before reading or changing data.
The legacy `/admin_users` command remains available.

## Tech stack

- Python 3.12+
- aiogram 3
- OpenAI API
- SQLite and aiosqlite
- python-dotenv
- unittest

## Installation

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/<username>/VoiceTextAI.git
cd VoiceTextAI

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Environment variables

Copy the example configuration:

```bash
cp .env.example .env
```

Configure the following values:

```dotenv
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
ADMIN_IDS=123456789,987654321
```

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token from BotFather |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `ADMIN_IDS` | No | Comma-separated Telegram IDs with admin access |

Never commit `.env`. It is excluded by `.gitignore`.

## Run locally

```bash
python3 main.py
```

The bot uses Telegram long polling. SQLite tables and migrations are created
automatically in `data/voicetext.db`.

## Tests

Run the complete test suite:

```bash
python3 -m unittest discover -s tests -v
```

Tests cover usage limits, database migrations, AI callbacks, translations,
history, referrals, profile updates and the inline admin panel.

## Screenshots

Screenshots will be added before the public launch.

| Voice processing | AI actions | Admin panel |
| --- | --- | --- |
| _Coming soon_ | _Coming soon_ | _Coming soon_ |

Suggested location for future images: `docs/screenshots/`.

## Roadmap

- [ ] Telegram Stars payments
- [ ] VPS deployment and process management
- [ ] Product analytics
- [ ] Search and filters in the admin panel
- [ ] User-selectable translation languages
- [ ] Exportable message history

## License

Distributed under the [MIT License](LICENSE).

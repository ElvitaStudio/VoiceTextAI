# Release Notes

## VoiceText AI v1.4

VoiceText AI v1.4 is the current GitHub-ready release of the Telegram bot.

### Voice processing

- Telegram voice-message download and validation
- OpenAI Speech-to-Text transcription
- Grammar, punctuation and filler-word cleanup
- Free, Pro and Premium voice limits
- Automatic release of usage reservations after processing failures

### AI actions

- Improve text
- Business style
- Summary
- Telegram post
- Email
- Task extraction
- Translation into 15 supported languages
- Separate daily limits for AI actions and translations

### User experience

- Inline text-action keyboard
- Decorated and Telegram-safe result messages
- `/start`, `/help`, `/limits`, `/history`, `/premium` and `/invite`
- Plan-based message history
- Long-message splitting

### Plans

- Free: 10 voice messages, 5 AI actions and 5 translations per day
- Pro: 100 voice messages, 50 AI actions and 50 translations per day
- Premium: 1000 voice messages with unlimited AI actions and translations

### Translation languages

- Existing languages remain supported: 🇷🇺 Русский, 🇬🇧 English,
  🇺🇦 Українська, 🇩🇪 Deutsch, 🇵🇱 Polski, 🇪🇸 Español,
  🇫🇷 Français and 🇮🇹 Italiano
- New languages: 🇹🇷 Türkçe, 🇵🇹 Português, 🇦🇿 Azərbaycan,
  🇷🇴 Română, 🇨🇿 Čeština, 🇷🇸 Српски and 🇳🇱 Nederlands

### Referral system

- Personal deep links through `/invite`
- Premium reward for 3 days
- Self-referral protection
- Atomic one-time rewards

### Administration

- Admin access configured through `ADMIN_IDS`
- Inline `/admin` panel
- Paginated user list and detailed user cards
- Free, Pro and Premium plan management
- Temporary Premium extension
- Product and usage statistics
- Referral totals, top inviters and referral history
- Legacy `/admin_users` command
- Prepared broadcast text for the update; automatic sending is not enabled

Prepared broadcast text:

```text
🎉 Большое обновление VoiceText AI!

✨ Бесплатный лимит увеличен до 10 голосовых сообщений в сутки.

🌍 Добавлены новые языки перевода:

🇹🇷 Türkçe
🇵🇹 Português
🇦🇿 Azərbaycan
🇷🇴 Română
🇨🇿 Čeština
🇷🇸 Српски
🇳🇱 Nederlands

⚡ Улучшены AI-функции и работа бота.

🚀 Попробуйте новые возможности прямо сейчас!

Спасибо, что пользуетесь VoiceText AI ❤️
```

### Telegram Stars payments

- Pro invoice for 250 Stars and 30 days
- Premium invoice for 500 Stars and 30 days
- XTR currency with an empty provider token for digital goods
- Pre-checkout payload, owner, currency and amount validation
- Idempotent successful-payment processing
- Payment history stored with Telegram payment charge IDs
- `/paysupport` payment support command

### Data and quality

- SQLite storage and automatic migrations
- User profile synchronization
- Separate voice, AI-action and translation usage tables
- Automated unittest coverage for core bot functionality

### Known limitations

- Production deployment and analytics are planned for later releases

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
- Translation into supported languages
- Separate daily limits for AI actions and translations

### User experience

- Inline text-action keyboard
- Decorated and Telegram-safe result messages
- `/start`, `/help`, `/limits`, `/history`, `/premium` and `/invite`
- Plan-based message history
- Long-message splitting

### Plans

- Free: 5 voice messages, 1 AI action and 1 translation per day
- Pro: 100 voice messages, 10 AI actions and 5 translations per day
- Premium: 1000 voice messages with unlimited AI actions and translations

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

### Data and quality

- SQLite storage and automatic migrations
- User profile synchronization
- Separate voice, AI-action and translation usage tables
- Automated unittest coverage for core bot functionality

### Known limitations

- Telegram Stars payment buttons are placeholders
- Production deployment and analytics are planned for later releases

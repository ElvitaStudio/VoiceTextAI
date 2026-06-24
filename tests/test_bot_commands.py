import unittest

from aiogram.types import BotCommandScopeChat

from app.bot import ADMIN_COMMANDS, USER_COMMANDS, set_commands
from app.config import Settings


class FakeBot:
    def __init__(self) -> None:
        self.calls = []

    async def set_my_commands(self, commands, scope=None) -> None:
        self.calls.append((commands, scope))


class BotCommandsTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_commands_do_not_include_admin_commands(self) -> None:
        bot = FakeBot()
        settings = Settings("token", "key", admin_ids=frozenset())

        await set_commands(bot, settings)

        self.assertEqual(len(bot.calls), 1)
        commands, scope = bot.calls[0]
        self.assertIsNone(scope)
        names = [command.command for command in commands]
        self.assertEqual(
            names,
            [
                "start",
                "help",
                "limits",
                "history",
                "premium",
                "paysupport",
                "invite",
            ],
        )
        self.assertNotIn("admin", names)
        self.assertNotIn("broadcast", names)
        self.assertEqual(commands, USER_COMMANDS)

    async def test_admin_commands_include_admin_and_broadcast(self) -> None:
        bot = FakeBot()
        settings = Settings("token", "key", admin_ids=frozenset({11, 22}))

        await set_commands(bot, settings)

        self.assertEqual(len(bot.calls), 3)
        user_commands, user_scope = bot.calls[0]
        self.assertEqual(user_commands, USER_COMMANDS)
        self.assertIsNone(user_scope)
        admin_scopes = [call[1] for call in bot.calls[1:]]
        self.assertTrue(
            all(isinstance(scope, BotCommandScopeChat) for scope in admin_scopes)
        )
        self.assertEqual(
            {scope.chat_id for scope in admin_scopes},
            {11, 22},
        )

        for commands, _scope in bot.calls[1:]:
            names = [command.command for command in commands]
            self.assertEqual(commands, ADMIN_COMMANDS)
            self.assertIn("admin", names)
            self.assertIn("broadcast", names)

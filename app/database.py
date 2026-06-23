from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import AsyncIterator
import logging

import aiosqlite

from app.plans import FREE, PREMIUM, PRO, VALID_PLANS, get_plan_limits


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class User:
    id: int
    telegram_id: int
    plan: str
    referred_by: int | None = None
    premium_until: str | None = None
    plan_until: str | None = None
    is_admin: bool = False

    @property
    def is_premium(self) -> bool:
        return self.is_admin or self.plan == PREMIUM

    @property
    def effective_plan(self) -> str:
        return PREMIUM if self.is_admin else self.plan


@dataclass(frozen=True, slots=True)
class Usage:
    used: int
    limit: int | None
    plan: str

    @property
    def remaining(self) -> int | None:
        if self.limit is None:
            return None
        return max(0, self.limit - self.used)


@dataclass(frozen=True, slots=True)
class AIUsage:
    ai_actions_used: int
    ai_actions_limit: int | None
    translations_used: int
    translations_limit: int | None

    @property
    def ai_actions_remaining(self) -> int | None:
        if self.ai_actions_limit is None:
            return None
        return max(0, self.ai_actions_limit - self.ai_actions_used)

    @property
    def translations_remaining(self) -> int | None:
        if self.translations_limit is None:
            return None
        return max(0, self.translations_limit - self.translations_used)


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: int
    user_id: int
    raw_text: str
    formatted_text: str


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    created_at: str
    formatted_text: str


@dataclass(frozen=True, slots=True)
class AdminUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    full_name: str | None
    plan: str
    premium_until: str | None
    created_at: str | None
    user_id: int = 0
    voice_messages_used: int = 0
    ai_actions_today: int = 0
    translations_today: int = 0
    referrals_count: int = 0

    @property
    def display_name(self) -> str:
        if self.full_name:
            return self.full_name
        name = " ".join(
            part for part in (self.first_name, self.last_name) if part
        )
        return name or "—"


@dataclass(frozen=True, slots=True)
class AdminStatistics:
    total_users: int
    free_users: int
    pro_users: int
    premium_users: int
    users_today: int
    voice_messages_total: int
    ai_actions_today: int
    translations_today: int


@dataclass(frozen=True, slots=True)
class AdminUserPage:
    users: list[AdminUser]
    page: int
    total_users: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class AdminReferrer:
    user_id: int
    display_name: str
    username: str | None
    invited_count: int


@dataclass(frozen=True, slots=True)
class AdminReferral:
    inviter_name: str
    inviter_username: str | None
    invited_name: str
    invited_username: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class AdminReferralReport:
    total_referrals: int
    top_referrers: list[AdminReferrer]
    referrals: list[AdminReferral]


@dataclass(frozen=True, slots=True)
class Payment:
    id: int
    user_id: int
    plan: str
    currency: str
    amount: int
    payload: str
    telegram_payment_charge_id: str
    provider_payment_charge_id: str
    created_at: str


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    user: User
    created: bool
    referral_rewarded: bool
    rewarded_referrer_telegram_id: int | None = None
    reward_until: str | None = None


class Database:
    def __init__(
        self,
        path: Path,
        daily_free_limit: int | None = None,
        admin_ids: frozenset[int] = frozenset(),
    ) -> None:
        self.path = path
        # Kept for compatibility with the existing constructor.
        self.daily_free_limit = daily_free_limit
        self.admin_ids = admin_ids

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as db:
            await db.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    full_name TEXT,
                    is_premium INTEGER NOT NULL DEFAULT 0,
                    plan TEXT NOT NULL DEFAULT 'free',
                    referred_by INTEGER,
                    premium_until TEXT,
                    plan_until TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (referred_by)
                        REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS usage_limits (
                    user_id INTEGER NOT NULL,
                    usage_date TEXT NOT NULL,
                    used_count INTEGER NOT NULL DEFAULT 0
                        CHECK (used_count >= 0),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, usage_date),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ai_usage_limits (
                    user_id INTEGER NOT NULL,
                    usage_date TEXT NOT NULL,
                    ai_actions_count INTEGER NOT NULL DEFAULT 0
                        CHECK (ai_actions_count >= 0),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, usage_date),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS translation_usage_limits (
                    user_id INTEGER NOT NULL,
                    usage_date TEXT NOT NULL,
                    translations_count INTEGER NOT NULL DEFAULT 0
                        CHECK (translations_count >= 0),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, usage_date),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    telegram_message_id INTEGER NOT NULL,
                    telegram_file_id TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    raw_text TEXT,
                    formatted_text TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_user_created
                    ON messages(user_id, created_at);

                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inviter_id INTEGER NOT NULL,
                    invited_id INTEGER NOT NULL UNIQUE,
                    reward_days INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (inviter_id)
                        REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (invited_id)
                        REFERENCES users(id) ON DELETE CASCADE,
                    CHECK (inviter_id != invited_id)
                );

                CREATE INDEX IF NOT EXISTS idx_referrals_inviter
                    ON referrals(inviter_id, created_at);

                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    payload TEXT NOT NULL,
                    telegram_payment_charge_id TEXT NOT NULL UNIQUE,
                    provider_payment_charge_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_payments_user_created
                    ON payments(user_id, created_at);
                """
            )
            await self._migrate_ai_usage_tables(db)
            cursor = await db.execute("PRAGMA table_info(users)")
            columns = {row[1] for row in await cursor.fetchall()}
            profile_columns = {
                "username": "TEXT",
                "first_name": "TEXT",
                "last_name": "TEXT",
                "full_name": "TEXT",
            }
            for column, column_type in profile_columns.items():
                if column not in columns:
                    await db.execute(
                        f"ALTER TABLE users ADD COLUMN {column} {column_type}"
                    )
            if "plan" not in columns:
                await db.execute(
                    "ALTER TABLE users "
                    "ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'"
                )
            if "referred_by" not in columns:
                await db.execute(
                    "ALTER TABLE users ADD COLUMN referred_by INTEGER"
                )
            if "premium_until" not in columns:
                await db.execute(
                    "ALTER TABLE users ADD COLUMN premium_until TEXT"
                )
            if "plan_until" not in columns:
                await db.execute(
                    "ALTER TABLE users ADD COLUMN plan_until TEXT"
                )
            await db.execute(
                """
                UPDATE users
                SET plan = 'premium'
                WHERE is_premium = 1 AND plan = 'free'
                """
            )
            await db.execute(
                """
                UPDATE users
                SET plan = 'free'
                WHERE plan NOT IN ('free', 'pro', 'premium')
                """
            )
            await db.execute(
                """
                UPDATE users
                SET full_name = TRIM(
                    COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')
                )
                WHERE full_name IS NULL OR full_name = ''
                """
            )
            await db.commit()

    async def _migrate_ai_usage_tables(
        self,
        db: aiosqlite.Connection,
    ) -> None:
        cursor = await db.execute("PRAGMA table_info(ai_usage_limits)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "translations_count" not in columns:
            return

        await db.executescript(
            """
            DROP TABLE IF EXISTS ai_usage_limits_v121;

            CREATE TABLE ai_usage_limits_v121 (
                user_id INTEGER NOT NULL,
                usage_date TEXT NOT NULL,
                ai_actions_count INTEGER NOT NULL DEFAULT 0
                    CHECK (ai_actions_count >= 0),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, usage_date),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            INSERT INTO ai_usage_limits_v121 (
                user_id,
                usage_date,
                ai_actions_count,
                updated_at
            )
            SELECT
                user_id,
                usage_date,
                ai_actions_count,
                updated_at
            FROM ai_usage_limits;

            INSERT INTO translation_usage_limits (
                user_id,
                usage_date,
                translations_count,
                updated_at
            )
            SELECT
                user_id,
                usage_date,
                translations_count,
                updated_at
            FROM ai_usage_limits
            WHERE translations_count > 0
            ON CONFLICT(user_id, usage_date) DO UPDATE SET
                translations_count = MAX(
                    translation_usage_limits.translations_count,
                    excluded.translations_count
                ),
                updated_at = excluded.updated_at;

            DROP TABLE ai_usage_limits;
            ALTER TABLE ai_usage_limits_v121 RENAME TO ai_usage_limits;
            """
        )

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        db = await aiosqlite.connect(self.path, timeout=30)
        try:
            await db.execute("PRAGMA foreign_keys = ON")
            yield db
        finally:
            await db.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    async def upsert_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None = None,
        full_name: str | None = None,
    ) -> User:
        result = await self.register_user(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
        )
        return result.user

    async def register_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        referred_by_telegram_id: int | None = None,
        reward_days: int = 3,
        last_name: str | None = None,
        full_name: str | None = None,
    ) -> RegistrationResult:
        now = self._now()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                """
                SELECT
                    id,
                    telegram_id,
                    plan,
                    is_premium,
                    referred_by,
                    premium_until,
                    plan_until
                FROM users
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                await db.execute(
                    """
                    UPDATE users
                    SET username = ?,
                        first_name = ?,
                        last_name = ?,
                        full_name = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        username,
                        first_name,
                        last_name,
                        full_name,
                        now,
                        existing["id"],
                    ),
                )
                await db.commit()
                if referred_by_telegram_id is not None:
                    logger.info(
                        "Referral ignored for existing user %s",
                        telegram_id,
                    )
                return RegistrationResult(
                    user=self._row_to_user(existing),
                    created=False,
                    referral_rewarded=False,
                )

            cursor = await db.execute(
                """
                INSERT INTO users (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    full_name,
                    plan,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'free', ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    full_name = excluded.full_name,
                    updated_at = excluded.updated_at
                """,
                (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    full_name,
                    now,
                    now,
                ),
            )
            user_id = int(cursor.lastrowid)
            referral_rewarded = False
            rewarded_referrer_telegram_id: int | None = None
            reward_until: str | None = None

            if referred_by_telegram_id == telegram_id:
                logger.info(
                    "Self-referral rejected for Telegram user %s",
                    telegram_id,
                )
            elif referred_by_telegram_id is not None:
                cursor = await db.execute(
                    """
                    SELECT
                        id,
                        telegram_id,
                        plan,
                        plan_until,
                        premium_until
                    FROM users
                    WHERE telegram_id = ?
                    """,
                    (referred_by_telegram_id,),
                )
                inviter = await cursor.fetchone()
                if inviter is not None:
                    cursor = await db.execute(
                        """
                        INSERT OR IGNORE INTO referrals (
                            inviter_id,
                            invited_id,
                            reward_days,
                            created_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (inviter["id"], user_id, reward_days, now),
                    )
                    if cursor.rowcount == 1:
                        reward_until = self._extend_referral_until(
                            inviter["plan_until"],
                            inviter["premium_until"],
                            reward_days,
                        )
                        await db.execute(
                            """
                            UPDATE users
                            SET plan = 'premium',
                                is_premium = 1,
                                plan_until = ?,
                                premium_until = ?,
                                updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                reward_until,
                                reward_until,
                                now,
                                inviter["id"],
                            ),
                        )
                        await db.execute(
                            """
                            UPDATE users
                            SET referred_by = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (inviter["id"], now, user_id),
                        )
                        referral_rewarded = True
                        rewarded_referrer_telegram_id = int(
                            inviter["telegram_id"]
                        )
                        logger.info(
                            "Referral rewarded: inviter=%s invitee=%s "
                            "premium_until=%s",
                            rewarded_referrer_telegram_id,
                            telegram_id,
                            reward_until,
                        )
                    else:
                        logger.info(
                            "Duplicate referral ignored: invitee=%s",
                            telegram_id,
                        )
                else:
                    logger.info(
                        "Referral inviter not found: inviter=%s invitee=%s",
                        referred_by_telegram_id,
                        telegram_id,
                    )

            cursor = await db.execute(
                """
                SELECT
                    id,
                    telegram_id,
                    plan,
                    is_premium,
                    referred_by,
                    premium_until,
                    plan_until
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            await db.commit()

        if row is None:
            raise RuntimeError("Failed to create or load user")
        return RegistrationResult(
            user=self._row_to_user(row),
            created=True,
            referral_rewarded=referral_rewarded,
            rewarded_referrer_telegram_id=(
                rewarded_referrer_telegram_id
            ),
            reward_until=reward_until,
        )

    def _row_to_user(self, row: aiosqlite.Row) -> User:
        plan = row["plan"]
        row_keys = row.keys()
        plan_until = (
            row["plan_until"] if "plan_until" in row_keys else None
        )
        if plan_until is not None and not self._is_future(plan_until):
            plan = FREE
        elif bool(row["is_premium"]) and plan == FREE:
            plan = PREMIUM
        if plan not in VALID_PLANS:
            plan = FREE
        premium_until = row["premium_until"]
        if (
            plan != PREMIUM
            and premium_until is not None
            and self._is_future(premium_until)
        ):
            plan = PREMIUM
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            plan=plan,
            referred_by=row["referred_by"],
            premium_until=premium_until,
            plan_until=plan_until,
            is_admin=row["telegram_id"] in self.admin_ids,
        )

    @staticmethod
    def _is_future(value: str) -> bool:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed > datetime.now(timezone.utc)

    @staticmethod
    def _extend_premium_until(
        current_value: str | None,
        reward_days: int,
    ) -> str:
        now = datetime.now(timezone.utc)
        base = now
        if current_value:
            try:
                current = datetime.fromisoformat(current_value)
                if current.tzinfo is None:
                    current = current.replace(tzinfo=timezone.utc)
                if current > now:
                    base = current
            except ValueError:
                pass
        return (base + timedelta(days=reward_days)).isoformat()

    @staticmethod
    def _extend_referral_until(
        plan_until: str | None,
        premium_until: str | None,
        reward_days: int,
    ) -> str:
        now = datetime.now(timezone.utc)
        base = now
        for value in (plan_until, premium_until):
            if not value:
                continue
            try:
                current = datetime.fromisoformat(value)
            except ValueError:
                continue
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            if current > base:
                base = current
        return (base + timedelta(days=reward_days)).isoformat()

    @staticmethod
    def _extend_until(
        current_value: str | None,
        days: int,
    ) -> str:
        now = datetime.now(timezone.utc)
        base = now
        if current_value:
            try:
                current = datetime.fromisoformat(current_value)
                if current.tzinfo is None:
                    current = current.replace(tzinfo=timezone.utc)
                if current > now:
                    base = current
            except ValueError:
                pass
        return (base + timedelta(days=days)).isoformat()

    async def get_referral_count(self, inviter_user_id: int) -> int:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*)
                FROM referrals
                WHERE inviter_id = ?
                """,
                (inviter_user_id,),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_admin_users(self) -> list[AdminUser]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    id,
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    full_name,
                    plan,
                    is_premium,
                    referred_by,
                    premium_until,
                    plan_until,
                    created_at
                FROM users
                ORDER BY created_at DESC, id DESC
                """
            )
            rows = await cursor.fetchall()

        users: list[AdminUser] = []
        for row in rows:
            effective_plan = self._row_to_user(row).plan
            users.append(
                AdminUser(
                    user_id=row["id"],
                    telegram_id=row["telegram_id"],
                    username=row["username"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    full_name=row["full_name"],
                    plan=effective_plan,
                    premium_until=row["premium_until"],
                    created_at=row["created_at"],
                )
            )
        return users

    async def get_admin_statistics(self) -> AdminStatistics:
        today = self._today()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    id,
                    telegram_id,
                    plan,
                    is_premium,
                    referred_by,
                    premium_until,
                    plan_until,
                    created_at
                FROM users
                """
            )
            user_rows = await cursor.fetchall()
            cursor = await db.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE status = 'completed'
                """
            )
            voice_row = await cursor.fetchone()
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(ai_actions_count), 0)
                FROM ai_usage_limits
                WHERE usage_date = ?
                """,
                (today,),
            )
            ai_row = await cursor.fetchone()
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(translations_count), 0)
                FROM translation_usage_limits
                WHERE usage_date = ?
                """,
                (today,),
            )
            translation_row = await cursor.fetchone()

        plan_counts = {FREE: 0, PRO: 0, PREMIUM: 0}
        users_today = 0
        for row in user_rows:
            plan_counts[self._row_to_user(row).plan] += 1
            created_at = row["created_at"] or ""
            if created_at.startswith(today):
                users_today += 1

        return AdminStatistics(
            total_users=len(user_rows),
            free_users=plan_counts[FREE],
            pro_users=plan_counts[PRO],
            premium_users=plan_counts[PREMIUM],
            users_today=users_today,
            voice_messages_total=int(voice_row[0]) if voice_row else 0,
            ai_actions_today=int(ai_row[0]) if ai_row else 0,
            translations_today=(
                int(translation_row[0]) if translation_row else 0
            ),
        )

    async def get_admin_users_page(
        self,
        page: int,
        page_size: int = 10,
    ) -> AdminUserPage:
        page_size = max(1, min(page_size, 50))
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            count_row = await cursor.fetchone()
            total_users = int(count_row[0]) if count_row else 0
            total_pages = max(1, (total_users + page_size - 1) // page_size)
            current_page = min(max(page, 0), total_pages - 1)
            cursor = await db.execute(
                """
                SELECT
                    id,
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    full_name,
                    plan,
                    is_premium,
                    referred_by,
                    premium_until,
                    plan_until,
                    created_at
                FROM users
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, current_page * page_size),
            )
            rows = await cursor.fetchall()

        users = [
            AdminUser(
                user_id=row["id"],
                telegram_id=row["telegram_id"],
                username=row["username"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                full_name=row["full_name"],
                plan=self._row_to_user(row).plan,
                premium_until=row["premium_until"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
        return AdminUserPage(
            users=users,
            page=current_page,
            total_users=total_users,
            total_pages=total_pages,
        )

    async def get_admin_user(self, user_id: int) -> AdminUser | None:
        today = self._today()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    u.id,
                    u.telegram_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    u.full_name,
                    u.plan,
                    u.is_premium,
                    u.referred_by,
                    u.premium_until,
                    u.plan_until,
                    u.created_at,
                    (
                        SELECT COUNT(*)
                        FROM messages AS m
                        WHERE m.user_id = u.id
                          AND m.status = 'completed'
                    ) AS voice_messages_used,
                    COALESCE((
                        SELECT a.ai_actions_count
                        FROM ai_usage_limits AS a
                        WHERE a.user_id = u.id
                          AND a.usage_date = ?
                    ), 0) AS ai_actions_today,
                    COALESCE((
                        SELECT t.translations_count
                        FROM translation_usage_limits AS t
                        WHERE t.user_id = u.id
                          AND t.usage_date = ?
                    ), 0) AS translations_today,
                    (
                        SELECT COUNT(*)
                        FROM referrals AS r
                        WHERE r.inviter_id = u.id
                    ) AS referrals_count
                FROM users AS u
                WHERE u.id = ?
                """,
                (today, today, user_id),
            )
            row = await cursor.fetchone()

        if row is None:
            return None
        return AdminUser(
            user_id=row["id"],
            telegram_id=row["telegram_id"],
            username=row["username"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            full_name=row["full_name"],
            plan=self._row_to_user(row).plan,
            premium_until=row["premium_until"],
            created_at=row["created_at"],
            voice_messages_used=row["voice_messages_used"],
            ai_actions_today=row["ai_actions_today"],
            translations_today=row["translations_today"],
            referrals_count=row["referrals_count"],
        )

    async def extend_admin_user_premium(
        self,
        user_id: int,
        days: int = 3,
    ) -> bool:
        if days <= 0:
            raise ValueError("Premium extension must be positive")
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT premium_until FROM users WHERE id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                await db.rollback()
                return False
            premium_until = self._extend_premium_until(
                row["premium_until"],
                days,
            )
            await db.execute(
                """
                UPDATE users
                SET premium_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (premium_until, self._now(), user_id),
            )
            await db.commit()
        return True

    async def set_admin_user_plan(self, user_id: int, plan: str) -> bool:
        if plan not in VALID_PLANS:
            raise ValueError(f"Unsupported plan: {plan}")
        premium_until_sql = (
            "premium_until" if plan == PREMIUM else "NULL"
        )
        async with self._connect() as db:
            cursor = await db.execute(
                f"""
                UPDATE users
                SET plan = ?,
                    is_premium = ?,
                    premium_until = {premium_until_sql},
                    plan_until = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (plan, int(plan == PREMIUM), self._now(), user_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def process_stars_payment(
        self,
        telegram_id: int,
        plan: str,
        currency: str,
        amount: int,
        payload: str,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str,
        duration_days: int = 30,
    ) -> bool:
        if plan not in {PRO, PREMIUM}:
            raise ValueError(f"Unsupported paid plan: {plan}")
        if currency != "XTR":
            raise ValueError("Telegram Stars payments must use XTR")
        if amount <= 0 or duration_days <= 0:
            raise ValueError("Payment amount and duration must be positive")
        if not telegram_payment_charge_id:
            raise ValueError("Telegram payment charge ID is required")

        now = self._now()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                """
                SELECT id, plan, plan_until
                FROM users
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
            user_row = await cursor.fetchone()
            if user_row is None:
                await db.rollback()
                return False

            cursor = await db.execute(
                """
                INSERT OR IGNORE INTO payments (
                    user_id,
                    plan,
                    currency,
                    amount,
                    payload,
                    telegram_payment_charge_id,
                    provider_payment_charge_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_row["id"],
                    plan,
                    currency,
                    amount,
                    payload,
                    telegram_payment_charge_id,
                    provider_payment_charge_id,
                    now,
                ),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                return False

            current_until = (
                user_row["plan_until"]
                if user_row["plan"] == plan
                else None
            )
            plan_until = self._extend_until(
                current_until,
                duration_days,
            )
            premium_until = plan_until if plan == PREMIUM else None
            await db.execute(
                """
                UPDATE users
                SET plan = ?,
                    is_premium = ?,
                    plan_until = ?,
                    premium_until = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    plan,
                    int(plan == PREMIUM),
                    plan_until,
                    premium_until,
                    now,
                    user_row["id"],
                ),
            )
            await db.commit()
        return True

    async def get_payment_by_charge_id(
        self,
        telegram_payment_charge_id: str,
    ) -> Payment | None:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    id,
                    user_id,
                    plan,
                    currency,
                    amount,
                    payload,
                    telegram_payment_charge_id,
                    provider_payment_charge_id,
                    created_at
                FROM payments
                WHERE telegram_payment_charge_id = ?
                """,
                (telegram_payment_charge_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return Payment(
            id=row["id"],
            user_id=row["user_id"],
            plan=row["plan"],
            currency=row["currency"],
            amount=row["amount"],
            payload=row["payload"],
            telegram_payment_charge_id=row[
                "telegram_payment_charge_id"
            ],
            provider_payment_charge_id=row[
                "provider_payment_charge_id"
            ],
            created_at=row["created_at"],
        )

    async def get_admin_referral_report(self) -> AdminReferralReport:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COUNT(*) FROM referrals")
            count_row = await cursor.fetchone()
            cursor = await db.execute(
                """
                SELECT
                    inviter.id AS user_id,
                    inviter.username,
                    inviter.first_name,
                    inviter.last_name,
                    inviter.full_name,
                    COUNT(*) AS invited_count
                FROM referrals AS r
                JOIN users AS inviter ON inviter.id = r.inviter_id
                GROUP BY inviter.id
                ORDER BY invited_count DESC, inviter.id
                LIMIT 10
                """
            )
            top_rows = await cursor.fetchall()
            cursor = await db.execute(
                """
                SELECT
                    inviter.username AS inviter_username,
                    inviter.first_name AS inviter_first_name,
                    inviter.last_name AS inviter_last_name,
                    inviter.full_name AS inviter_full_name,
                    invited.username AS invited_username,
                    invited.first_name AS invited_first_name,
                    invited.last_name AS invited_last_name,
                    invited.full_name AS invited_full_name,
                    r.created_at
                FROM referrals AS r
                JOIN users AS inviter ON inviter.id = r.inviter_id
                JOIN users AS invited ON invited.id = r.invited_id
                ORDER BY r.created_at DESC, r.id DESC
                """
            )
            referral_rows = await cursor.fetchall()

        def display_name(
            full_name: str | None,
            first_name: str | None,
            last_name: str | None,
        ) -> str:
            if full_name:
                return full_name
            return " ".join(
                part for part in (first_name, last_name) if part
            ) or "—"

        top_referrers = [
            AdminReferrer(
                user_id=row["user_id"],
                display_name=display_name(
                    row["full_name"],
                    row["first_name"],
                    row["last_name"],
                ),
                username=row["username"],
                invited_count=row["invited_count"],
            )
            for row in top_rows
        ]
        referrals = [
            AdminReferral(
                inviter_name=display_name(
                    row["inviter_full_name"],
                    row["inviter_first_name"],
                    row["inviter_last_name"],
                ),
                inviter_username=row["inviter_username"],
                invited_name=display_name(
                    row["invited_full_name"],
                    row["invited_first_name"],
                    row["invited_last_name"],
                ),
                invited_username=row["invited_username"],
                created_at=row["created_at"],
            )
            for row in referral_rows
        ]
        return AdminReferralReport(
            total_referrals=int(count_row[0]) if count_row else 0,
            top_referrers=top_referrers,
            referrals=referrals,
        )

    async def reserve_usage(self, user: User) -> tuple[bool, int]:
        if user.is_admin:
            return True, 0
        limit = get_plan_limits(user.effective_plan).voice_daily_limit
        if limit is None:
            return True, 0

        today = self._today()
        now = self._now()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                INSERT INTO usage_limits (
                    user_id, usage_date, used_count, updated_at
                )
                VALUES (?, ?, 0, ?)
                ON CONFLICT(user_id, usage_date) DO NOTHING
                """,
                (user.id, today, now),
            )
            cursor = await db.execute(
                """
                SELECT used_count
                FROM usage_limits
                WHERE user_id = ? AND usage_date = ?
                """,
                (user.id, today),
            )
            row = await cursor.fetchone()
            used = int(row["used_count"]) if row else 0

            if used >= limit:
                await db.rollback()
                return False, used

            used += 1
            await db.execute(
                """
                UPDATE usage_limits
                SET used_count = ?, updated_at = ?
                WHERE user_id = ? AND usage_date = ?
                """,
                (used, now, user.id, today),
            )
            await db.commit()
            return True, used

    async def release_usage(self, user: User) -> None:
        if (
            user.is_admin
            or get_plan_limits(user.effective_plan).voice_daily_limit is None
        ):
            return

        async with self._connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                UPDATE usage_limits
                SET used_count = MAX(used_count - 1, 0), updated_at = ?
                WHERE user_id = ? AND usage_date = ?
                """,
                (self._now(), user.id, self._today()),
            )
            await db.commit()

    async def get_usage(self, user: User) -> Usage:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT used_count
                FROM usage_limits
                WHERE user_id = ? AND usage_date = ?
                """,
                (user.id, self._today()),
            )
            row = await cursor.fetchone()
        used = int(row[0]) if row else 0
        return Usage(
            used=used,
            limit=(
                None
                if user.is_admin
                else get_plan_limits(user.effective_plan).voice_daily_limit
            ),
            plan=user.effective_plan,
        )

    async def reserve_ai_action(
        self,
        user: User,
    ) -> bool:
        if user.is_admin:
            return True
        limits = get_plan_limits(user.effective_plan)
        limit = limits.ai_actions_daily_limit
        if limit is None:
            return True

        today = self._today()
        now = self._now()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                INSERT INTO ai_usage_limits (
                    user_id,
                    usage_date,
                    ai_actions_count,
                    updated_at
                )
                VALUES (?, ?, 0, ?)
                ON CONFLICT(user_id, usage_date) DO NOTHING
                """,
                (user.id, today, now),
            )
            cursor = await db.execute(
                f"""
                SELECT ai_actions_count
                FROM ai_usage_limits
                WHERE user_id = ? AND usage_date = ?
                """,
                (user.id, today),
            )
            row = await cursor.fetchone()
            used = int(row["ai_actions_count"]) if row else 0
            if used >= limit:
                await db.rollback()
                return False

            await db.execute(
                f"""
                UPDATE ai_usage_limits
                SET ai_actions_count = ai_actions_count + 1,
                    updated_at = ?
                WHERE user_id = ? AND usage_date = ?
                """,
                (now, user.id, today),
            )
            await db.commit()
            return True

    async def release_ai_action(
        self,
        user: User,
    ) -> None:
        if (
            user.is_admin
            or get_plan_limits(user.effective_plan).ai_actions_daily_limit
            is None
        ):
            return

        async with self._connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                f"""
                UPDATE ai_usage_limits
                SET ai_actions_count = MAX(ai_actions_count - 1, 0),
                    updated_at = ?
                WHERE user_id = ? AND usage_date = ?
                """,
                (self._now(), user.id, self._today()),
            )
            await db.commit()

    async def reserve_translation(self, user: User) -> bool:
        if user.is_admin:
            return True
        limit = get_plan_limits(user.effective_plan).translations_daily_limit
        if limit is None:
            return True

        today = self._today()
        now = self._now()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                INSERT INTO translation_usage_limits (
                    user_id,
                    usage_date,
                    translations_count,
                    updated_at
                )
                VALUES (?, ?, 0, ?)
                ON CONFLICT(user_id, usage_date) DO NOTHING
                """,
                (user.id, today, now),
            )
            cursor = await db.execute(
                """
                SELECT translations_count
                FROM translation_usage_limits
                WHERE user_id = ? AND usage_date = ?
                """,
                (user.id, today),
            )
            row = await cursor.fetchone()
            used = int(row["translations_count"]) if row else 0
            if used >= limit:
                await db.rollback()
                return False

            await db.execute(
                """
                UPDATE translation_usage_limits
                SET translations_count = translations_count + 1,
                    updated_at = ?
                WHERE user_id = ? AND usage_date = ?
                """,
                (now, user.id, today),
            )
            await db.commit()
            return True

    async def release_translation(self, user: User) -> None:
        if (
            user.is_admin
            or get_plan_limits(user.effective_plan).translations_daily_limit
            is None
        ):
            return

        async with self._connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                UPDATE translation_usage_limits
                SET translations_count = MAX(translations_count - 1, 0),
                    updated_at = ?
                WHERE user_id = ? AND usage_date = ?
                """,
                (self._now(), user.id, self._today()),
            )
            await db.commit()

    async def get_ai_usage(self, user: User) -> AIUsage:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT ai_actions_count
                FROM ai_usage_limits
                WHERE user_id = ? AND usage_date = ?
                """,
                (user.id, self._today()),
            )
            ai_row = await cursor.fetchone()
            cursor = await db.execute(
                """
                SELECT translations_count
                FROM translation_usage_limits
                WHERE user_id = ? AND usage_date = ?
                """,
                (user.id, self._today()),
            )
            translation_row = await cursor.fetchone()

        limits = get_plan_limits(user.effective_plan)
        return AIUsage(
            ai_actions_used=int(ai_row[0]) if ai_row else 0,
            ai_actions_limit=(
                None if user.is_admin else limits.ai_actions_daily_limit
            ),
            translations_used=(
                int(translation_row[0]) if translation_row else 0
            ),
            translations_limit=(
                None if user.is_admin else limits.translations_daily_limit
            ),
        )

    async def set_user_plan(self, telegram_id: int, plan: str) -> None:
        if plan not in VALID_PLANS:
            raise ValueError(f"Unsupported plan: {plan}")
        async with self._connect() as db:
            await db.execute(
                """
                UPDATE users
                SET plan = ?,
                    is_premium = ?,
                    plan_until = NULL,
                    premium_until = NULL,
                    updated_at = ?
                WHERE telegram_id = ?
                """,
                (plan, int(plan == PREMIUM), self._now(), telegram_id),
            )
            await db.commit()

    async def create_message(
        self,
        user_id: int,
        telegram_message_id: int,
        telegram_file_id: str,
        duration_seconds: int,
    ) -> int:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO messages (
                    user_id,
                    telegram_message_id,
                    telegram_file_id,
                    duration_seconds,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'processing', ?)
                """,
                (
                    user_id,
                    telegram_message_id,
                    telegram_file_id,
                    duration_seconds,
                    self._now(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def complete_message(
        self,
        message_id: int,
        raw_text: str,
        formatted_text: str,
    ) -> None:
        async with self._connect() as db:
            await db.execute(
                """
                UPDATE messages
                SET raw_text = ?,
                    formatted_text = ?,
                    status = 'completed',
                    completed_at = ?
                WHERE id = ?
                """,
                (raw_text, formatted_text, self._now(), message_id),
            )
            await db.commit()

    async def fail_message(self, message_id: int, error_message: str) -> None:
        async with self._connect() as db:
            await db.execute(
                """
                UPDATE messages
                SET status = 'failed',
                    error_message = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (error_message[:1000], self._now(), message_id),
            )
            await db.commit()

    async def get_completed_message(
        self,
        message_id: int,
        user_id: int,
    ) -> StoredMessage | None:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, user_id, raw_text, formatted_text
                FROM messages
                WHERE id = ?
                  AND user_id = ?
                  AND status = 'completed'
                  AND formatted_text IS NOT NULL
                """,
                (message_id, user_id),
            )
            row = await cursor.fetchone()

        if row is None:
            return None
        return StoredMessage(
            id=row["id"],
            user_id=row["user_id"],
            raw_text=row["raw_text"] or "",
            formatted_text=row["formatted_text"],
        )

    async def get_message_history(
        self,
        user: User,
    ) -> list[HistoryMessage]:
        limit = get_plan_limits(user.effective_plan).history_limit
        limit_clause = "" if user.is_admin else "LIMIT ?"
        params: tuple[int, ...] = (
            (user.id,) if user.is_admin else (user.id, limit)
        )
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT
                    COALESCE(completed_at, created_at) AS history_date,
                    formatted_text
                FROM messages
                WHERE user_id = ?
                  AND status = 'completed'
                  AND formatted_text IS NOT NULL
                ORDER BY history_date DESC, id DESC
                {limit_clause}
                """,
                params,
            )
            rows = await cursor.fetchall()

        return [
            HistoryMessage(
                created_at=row["history_date"],
                formatted_text=row["formatted_text"],
            )
            for row in rows
        ]

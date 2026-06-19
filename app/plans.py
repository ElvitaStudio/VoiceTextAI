from dataclasses import dataclass


FREE = "free"
PRO = "pro"
PREMIUM = "premium"
VALID_PLANS = {FREE, PRO, PREMIUM}


@dataclass(frozen=True, slots=True)
class PlanLimits:
    name: str
    voice_daily_limit: int | None
    max_voice_duration: int | None
    ai_actions_daily_limit: int | None
    translations_daily_limit: int | None
    history_limit: int


PLAN_LIMITS = {
    FREE: PlanLimits(
        name="Free",
        voice_daily_limit=5,
        max_voice_duration=120,
        ai_actions_daily_limit=1,
        translations_daily_limit=1,
        history_limit=5,
    ),
    PRO: PlanLimits(
        name="Pro",
        voice_daily_limit=100,
        max_voice_duration=600,
        ai_actions_daily_limit=10,
        translations_daily_limit=5,
        history_limit=30,
    ),
    PREMIUM: PlanLimits(
        name="Premium",
        voice_daily_limit=1000,
        max_voice_duration=1800,
        ai_actions_daily_limit=None,
        translations_daily_limit=None,
        history_limit=100,
    ),
}


def get_plan_limits(plan: str) -> PlanLimits:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS[FREE])


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "без ограничений"

    minutes = seconds // 60
    if minutes % 10 == 1 and minutes % 100 != 11:
        word = "минута"
    elif minutes % 10 in {2, 3, 4} and minutes % 100 not in {12, 13, 14}:
        word = "минуты"
    else:
        word = "минут"
    return f"{minutes} {word}"

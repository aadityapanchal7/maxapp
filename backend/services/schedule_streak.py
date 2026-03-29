"""Master schedule daily streak — all merged tasks completed by local end-of-day."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from models.sqlalchemy_models import User
from services.schedule_master_merge import merged_day_all_completed

logger = logging.getLogger(__name__)

STREAK_KEY = "master_schedule_streak"
LAST_PERFECT_KEY = "master_schedule_streak_last_perfect_date"


def _user_tz(onboarding: dict | None) -> ZoneInfo:
    tz_name = str((onboarding or {}).get("timezone") or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def local_today_date(onboarding: dict | None) -> date:
    return datetime.now(_user_tz(onboarding)).date()


def _reconcile_missed(profile: dict[str, Any], today: date) -> bool:
    """If last perfect day is before yesterday, reset streak. Returns True if profile changed."""
    last_s = profile.get(LAST_PERFECT_KEY)
    if not last_s:
        return False
    try:
        last_d = date.fromisoformat(str(last_s))
    except (TypeError, ValueError):
        profile[LAST_PERFECT_KEY] = None
        profile[STREAK_KEY] = 0
        return True
    if last_d < today - timedelta(days=1):
        profile[STREAK_KEY] = 0
        profile[LAST_PERFECT_KEY] = None
        return True
    return False


def _credit_if_perfect_day(
    profile: dict[str, Any],
    schedules: list[dict],
    today: date,
) -> bool:
    """If merged view shows all tasks done for today, bump streak once per calendar day."""
    today_s = today.isoformat()
    if not merged_day_all_completed(schedules, today_s):
        return False
    last_s = profile.get(LAST_PERFECT_KEY)
    if last_s == today_s:
        return False

    current = int(profile.get(STREAK_KEY) or 0)
    try:
        last_d = date.fromisoformat(str(last_s)) if last_s else None
    except (TypeError, ValueError):
        last_d = None

    if last_d is None:
        new_streak = 1
    elif last_d == today - timedelta(days=1):
        new_streak = current + 1
    else:
        new_streak = 1

    profile[STREAK_KEY] = new_streak
    profile[LAST_PERFECT_KEY] = today_s
    return True


def streak_payload_from_profile(profile: dict[str, Any], today: date) -> dict[str, Any]:
    return {
        "current": int(profile.get(STREAK_KEY) or 0),
        "last_perfect_date": profile.get(LAST_PERFECT_KEY),
        "today_date": today.isoformat(),
    }


async def sync_master_schedule_streak(
    user: User | None,
    schedules: list[dict],
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Reconcile missed days, credit today if all merged tasks complete, persist profile.
    Returns streak payload for API clients.
    """
    if not user:
        return {"current": 0, "last_perfect_date": None, "today_date": date.today().isoformat()}

    onboarding = dict(user.onboarding or {})
    today = local_today_date(onboarding)
    profile = dict(user.profile or {})

    changed = _reconcile_missed(profile, today)
    changed = _credit_if_perfect_day(profile, schedules, today) or changed

    if changed:
        user.profile = profile
        flag_modified(user, "profile")
        user.updated_at = datetime.utcnow()
        await db.commit()

    return streak_payload_from_profile(profile, today)

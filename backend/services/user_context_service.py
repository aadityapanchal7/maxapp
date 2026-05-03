"""Per-user persistent context that influences future schedule generations.

The bot writes to this whenever it learns something relevant in chat —
product preferences, dislikes, frictions, equipment owned, allergies,
etc. The schedule generator reads from this on every generation/tweak.

Storage: `user_schedule_context` table, one row per user, JSONB blob.
Updates use Postgres JSONB merge (||) so concurrent writes don't clobber.

Conventions for keys (loose, expand as needed):
    product_preferences    {"cleanser": "cerave foaming"}
    product_dislikes       ["the ordinary niacinamide"]
    timing_preferences     {"workout": "evening"}
    skipped_repeatedly     ["skin.dermastamp"]
    morning_friction       "high" | "low"
    equipment_owned        ["dermastamp", "microneedle"]
    explicit_avoidances    ["mewing"]
    reported_issues        [{"date": "...", "note": "burning"}]
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Tiny LRU-ish cache (user_id -> (loaded_at, ctx)) — context is small and
# read on every generation. 60s TTL keeps it fresh without a DB roundtrip
# on chat-burst sequences.
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_S = 60.0


async def get_context(user_id: str, db: AsyncSession) -> dict[str, Any]:
    """Read merged context. Returns {} if no row exists yet."""
    cached = _CACHE.get(user_id)
    if cached and (time.time() - cached[0]) < _CACHE_TTL_S:
        return dict(cached[1])
    try:
        result = await db.execute(
            text("SELECT context FROM user_schedule_context WHERE user_id = :uid"),
            {"uid": UUID(user_id)},
        )
        row = result.first()
        ctx = dict(row[0]) if row and row[0] else {}
    except Exception as e:
        logger.warning("user_schedule_context fetch failed user=%s: %s", user_id, e)
        ctx = {}
    _CACHE[user_id] = (time.time(), ctx)
    return dict(ctx)


async def merge_context(user_id: str, updates: dict[str, Any], db: AsyncSession) -> dict:
    """Merge updates into the user's context (JSONB || semantics).

    Lists in `updates` REPLACE the corresponding existing list (we don't
    auto-dedupe-merge because the caller is the source of truth for
    intent — e.g. the bot *removing* a preference passes a new list).
    """
    if not updates:
        return await get_context(user_id, db)
    payload = json.dumps(updates)
    try:
        await db.execute(
            text(
                """
                INSERT INTO user_schedule_context (user_id, context)
                VALUES (:uid, CAST(:payload AS jsonb))
                ON CONFLICT (user_id) DO UPDATE
                    SET context = user_schedule_context.context || EXCLUDED.context,
                        updated_at = NOW()
                """
            ),
            {"uid": UUID(user_id), "payload": payload},
        )
    except Exception as e:
        logger.error("user_schedule_context merge failed user=%s: %s", user_id, e)
        raise
    _CACHE.pop(user_id, None)
    return await get_context(user_id, db)


async def append_to_list(user_id: str, key: str, value: Any, db: AsyncSession, *, max_len: int = 50) -> dict:
    """Append a value to a list-typed key, deduped, capped at max_len."""
    ctx = await get_context(user_id, db)
    lst = list(ctx.get(key) or [])
    if value not in lst:
        lst.append(value)
    if len(lst) > max_len:
        lst = lst[-max_len:]
    return await merge_context(user_id, {key: lst}, db)


def invalidate(user_id: str) -> None:
    _CACHE.pop(user_id, None)


def merged_user_state(onboarding: dict | None, context: dict | None, extras: dict | None = None) -> dict:
    """Single dict the DSL evaluates against. Precedence: extras > context > onboarding."""
    out: dict[str, Any] = {}
    if onboarding:
        out.update(onboarding)
    if context:
        out.update(context)
    if extras:
        out.update(extras)
    return out

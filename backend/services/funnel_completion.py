"""Post-funnel completion pass — runs AFTER onboarding.completed flips true.

Two jobs, both idempotent and safe to re-kick:

1. AUTO-ENROLL FIRST MAX (product decision 2026-08: picking a first max is
   REQUIRED — Day 1 must never show an empty planner). The quiz's picked maxes
   live only in ``onboarding.goals``; nothing else turns them into an active
   ``user_schedules`` row, so a brand-new user used to land on Main with
   "No habits for today". We build the TOP-priority pick here. Generation is
   LLM-backed with a ~60s ceiling, so this runs as a fire-and-forget task off
   the onboarding-save request — never inline (the funnel's final tap must not
   block on it).

2. SEED THE FUNNEL CONVERSATION into Max chat. The funnel has no real chat
   surface, so for a brand-new user the chat opened cold. We persist the quiz
   exchange as genuine ``chat_history`` rows (no LLM involved) so the main
   chat continues the conversation the funnel started.

Reliability: the enrollment intent is marked in ``onboarding`` as
``funnel_auto_enroll_pending`` BEFORE the task runs and cleared on success —
``GET /schedules/active/full`` (Home's hot read) re-kicks a pending intent, so
a task that died with the process still converges on the next app open.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm.attributes import flag_modified

from db.sqlalchemy import AsyncSessionLocal
from models.sqlalchemy_models import ChatConversation, ChatHistory, User, UserSchedule

logger = logging.getLogger(__name__)

# Known maxx ids, in the funnel's tile order (fallback ranking).
_KNOWN_MAXXES = ("skinmax", "fitmax", "hairmax", "heightmax", "bonemax")

_MAXX_LABELS = {
    "skinmax": "Skinmax",
    "fitmax": "Fitmax",
    "hairmax": "Hairmax",
    "heightmax": "Heightmax",
    "bonemax": "Bonemax",
}

_MOTIVATION_LINES = {
    "heartbreak": "someone broke my heart",
    "no_respect": "no one respects me",
    "event": "an upcoming date or event",
    "mog": "i just want to mog",
    "curious": "just curious",
}

_EFFORT_LINES = {
    "light": "light touch — some tips and tricks",
    "steady": "steady — tweaking my daily routine",
    "all_in": "all in — becoming a new person",
}

# Single-flight per process: a user id currently being processed. Guards the
# save-endpoint kick racing the active/full re-kick.
_in_flight: set[str] = set()


def kick_funnel_completion(user_id: str) -> None:
    """Fire-and-forget the completion pass for ``user_id`` (single-flight)."""
    uid = str(user_id)
    if uid in _in_flight:
        return
    _in_flight.add(uid)

    async def _run() -> None:
        try:
            await _complete(uid)
        except Exception:
            logger.exception("funnel completion pass failed for %s", uid)
        finally:
            _in_flight.discard(uid)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        # No running loop (sync caller in tests) — run inline.
        _in_flight.discard(uid)
        asyncio.run(_complete(uid))


def _ranked_picks(ob: dict) -> list[str]:
    """The user's picked maxes, best-first, as valid maxx ids."""
    goals = [g for g in (ob.get("goals") or []) if g in _KNOWN_MAXXES]
    if goals:
        return goals
    # Legacy/edge payloads: fall back to priority_order tokens.
    token_to_id = {"skin": "skinmax", "body": "fitmax", "hair": "hairmax",
                   "height": "heightmax", "face_structure": "bonemax"}
    return [token_to_id[t] for t in (ob.get("priority_order") or []) if t in token_to_id]


async def _active_maxx_count(db, user_uuid: UUID) -> int:
    res = await db.execute(
        select(func.count()).select_from(UserSchedule).where(
            (UserSchedule.user_id == user_uuid)
            & (UserSchedule.is_active == True)  # noqa: E712
            & (UserSchedule.maxx_id.isnot(None))
        )
    )
    return int(res.scalar() or 0)


async def _complete(user_id: str) -> None:
    user_uuid = UUID(user_id)

    # ── 1. Auto-enroll the top pick ────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_uuid)
        if user is None:
            return
        ob = dict(user.onboarding or {})
        if ob.get("completed") is not True:
            return
        picks = _ranked_picks(ob)
        needs_enroll = bool(picks) and (await _active_maxx_count(db, user_uuid)) == 0
        if needs_enroll:
            top = picks[0]
            try:
                from services.schedule_service import schedule_service
                await schedule_service.generate_maxx_schedule(
                    user_id=user_id,
                    maxx_id=top,
                    db=db,
                    wake_time=str(ob.get("wake_time") or "07:00"),
                    sleep_time=str(ob.get("sleep_time") or "23:00"),
                    subscription_tier=user.subscription_tier,
                )
                # Re-read: generate_maxx_schedule may itself have mutated
                # user.onboarding (per-maxx overrides) and committed.
                await db.refresh(user)
                ob = dict(user.onboarding or {})
                ob.pop("funnel_auto_enroll_pending", None)
                ob["funnel_auto_enrolled"] = top
                user.onboarding = ob
                flag_modified(user, "onboarding")
                await db.commit()
                logger.info("funnel auto-enroll: %s -> %s", user_id, top)
            except Exception:
                # Leave the pending marker in place — active/full re-kicks it.
                await db.rollback()
                logger.exception("funnel auto-enroll failed for %s (maxx=%s)", user_id, picks[0])
        elif ob.get("funnel_auto_enroll_pending"):
            # Already enrolled (or nothing to enroll) — clear a stale marker.
            ob.pop("funnel_auto_enroll_pending", None)
            user.onboarding = ob
            flag_modified(user, "onboarding")
            await db.commit()

    # ── 2. Seed the funnel conversation into Max chat ──────────────────────
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_uuid)
        if user is None:
            return
        ob = dict(user.onboarding or {})
        if ob.get("funnel_chat_seeded"):
            return
        existing = await db.execute(
            select(func.count()).select_from(ChatHistory).where(
                (ChatHistory.user_id == user_uuid)
                & ((ChatHistory.channel == "app") | (ChatHistory.channel.is_(None)))
            )
        )
        if int(existing.scalar() or 0) > 0:
            # The user already talked to Max — never inject above real history.
            ob["funnel_chat_seeded"] = True
            user.onboarding = ob
            flag_modified(user, "onboarding")
            await db.commit()
            return

        turns = _transcript(ob, first_name=(user.first_name or "").strip())
        convo = ChatConversation(user_id=user_uuid, title="getting started", channel="app")
        db.add(convo)
        await db.flush()
        now = datetime.utcnow()
        for i, (role, content) in enumerate(turns):
            db.add(ChatHistory(
                user_id=user_uuid,
                conversation_id=convo.id,
                role=role,
                content=content,
                channel="app",
                # Preserve order under identical commit timing.
                created_at=now.replace(microsecond=i * 1000),
            ))
        convo.last_message_at = now
        ob["funnel_chat_seeded"] = True
        user.onboarding = ob
        flag_modified(user, "onboarding")
        await db.commit()
        logger.info("funnel chat seeded for %s (%d turns)", user_id, len(turns))


def _transcript(ob: dict, first_name: str = "") -> list[tuple[str, str]]:
    """The funnel exchange as (role, content) turns — lowercase editorial voice."""
    picks = _ranked_picks(ob)
    pick_labels = " + ".join(_MAXX_LABELS[p] for p in picks) if picks else "not sure yet"
    motivation = _MOTIVATION_LINES.get(str(ob.get("motivation") or ""))
    if ob.get("motivation") == "other" and (ob.get("motivation_other") or "").strip():
        motivation = str(ob["motivation_other"]).strip()
    effort = _EFFORT_LINES.get(str(ob.get("effort_level") or ""))

    name_c = f", {first_name.lower()}" if first_name else ""
    turns: list[tuple[str, str]] = [
        ("assistant", f"hey{name_c} — picking up where setup left off. what are we working on?"),
        ("user", pick_labels),
    ]
    if motivation:
        turns += [
            ("assistant", "and what's pulling you here?"),
            ("user", motivation),
        ]
    if effort:
        turns += [
            ("assistant", "how hard do you want to go?"),
            ("user", effort),
        ]
    top_label = _MAXX_LABELS.get(picks[0], "your plan") if picks else "your plan"
    wake = str(ob.get("wake_time") or "").strip()
    wake_bit = f" around your {wake} wake" if wake else ""
    turns.append((
        "assistant",
        f"locked in. i built {top_label} into your day{wake_bit} — it's live on your planner. "
        "ask me anything, or tell me what to tweak.",
    ))
    return turns

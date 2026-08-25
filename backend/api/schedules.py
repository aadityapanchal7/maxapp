"""
Schedules API - AI-powered personalised schedules for course modules
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db, get_rds_db
from models.schedule import (
    GenerateScheduleRequest,
    GenerateMaxxScheduleRequest,
    SchedulePreferences,
    CompleteTaskRequest,
    AdaptScheduleRequest,
    EditTaskRequest,
)
from middleware.auth_middleware import get_current_user, require_paid_user
from services.schedule_service import schedule_service, ScheduleLimitError
from services.task_guide_service import get_task_guide, pregenerate_for_schedule
from services.schedule_streak import sync_master_schedule_streak
from models.sqlalchemy_models import User
from uuid import UUID

router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.post("/generate")
async def generate_schedule(
    data: GenerateScheduleRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Generate a personalised AI schedule for a course module"""
    try:
        schedule = await schedule_service.generate_schedule(
            user_id=current_user["id"],
            course_id=data.course_id,
            module_number=data.module_number,
            db=db,
            rds_db=rds_db,
            preferences=data.preferences.model_dump() if data.preferences else None,
            num_days=data.num_days,
            subscription_tier=current_user.get("subscription_tier"),
        )
        if isinstance(schedule, dict) and schedule.get("id"):
            background_tasks.add_task(
                pregenerate_for_schedule,
                str(schedule["id"]),
                str(current_user["id"]),
            )
        return {"schedule": schedule}
    except ScheduleLimitError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schedule generation failed: {e}")


@router.post("/generate-maxx")
async def generate_maxx_schedule(
    data: GenerateMaxxScheduleRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Generate a personalised AI schedule for a maxx module (e.g. Skinmax)"""
    try:
        schedule = await schedule_service.generate_maxx_schedule(
            user_id=current_user["id"],
            maxx_id=data.maxx_id,
            db=db,
            rds_db=rds_db,
            wake_time=data.wake_time,
            sleep_time=data.sleep_time,
            skin_concern=data.skin_concern,
            outside_today=data.outside_today,
            num_days=data.num_days,
            height_components=data.height_components,
            subscription_tier=current_user.get("subscription_tier"),
        )
        if isinstance(schedule, dict) and schedule.get("id"):
            background_tasks.add_task(
                pregenerate_for_schedule,
                str(schedule["id"]),
                str(current_user["id"]),
            )
        return {"schedule": schedule}
    except ScheduleLimitError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Maxx schedule generation failed: {e}")


@router.get("/maxx/{maxx_id}")
async def get_maxx_schedule(
    maxx_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's active schedule for a specific maxx"""
    schedule = await schedule_service.get_maxx_schedule(current_user["id"], maxx_id, db=db)
    if not schedule:
        return {"schedule": None, "message": f"No active {maxx_id} schedule. Start one from the module."}
    return {"schedule": schedule}


@router.get("/current")
async def get_current_schedule(
    course_id: str = None,
    module_number: int = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's current active schedule, optionally filtered by course/module"""
    schedule = await schedule_service.get_current_schedule(
        current_user["id"], db=db, course_id=course_id, module_number=module_number
    )
    if not schedule:
        return {"schedule": None, "message": "No active schedule. Generate one from a course module."}
    return {"schedule": schedule}


@router.get("/active/all")
async def get_all_active_schedules(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get count and labels of all active schedules for the user."""
    count, labels = await schedule_service.get_active_schedule_count(
        current_user["id"], db
    )
    tier = (current_user.get("subscription_tier") or "basic").lower()
    max_active = 3 if tier == "premium" else 2
    return {"count": count, "labels": labels, "max": max_active}


@router.get("/active/full")
async def get_all_active_schedules_full(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full schedule documents for all active modules (master schedule / merged week view)."""
    schedules = await schedule_service.get_all_active_schedules(current_user["id"], db)
    user_row = await db.get(User, UUID(current_user["id"]))
    # Self-heal a dropped funnel-completion pass: the auto-enroll intent is
    # committed WITH onboarding.completed, so if the fire-and-forget task died
    # (deploy, crash), the marker survives and this hot read re-kicks it.
    # Single-flight inside kick_funnel_completion keeps this free when racing.
    try:
        if (user_row.onboarding or {}).get("funnel_auto_enroll_pending"):
            from services.funnel_completion import kick_funnel_completion
            kick_funnel_completion(current_user["id"])
    except Exception:
        pass
    streak = await sync_master_schedule_streak(user_row, schedules, db)
    # Award any newly-earned badges off the freshly-synced day-state and hand
    # them back so the client can fire a celebration. Best-effort, never fatal.
    newly_earned: list = []
    try:
        from services.achievements import evaluate as _evaluate_achievements
        newly_earned = await _evaluate_achievements(db, user_row, streak=streak, schedules=schedules)
    except Exception:
        newly_earned = []
    # XP / rank block — pure dict reads off the freshly-synced profile. Best-effort.
    try:
        from services.gamification import gamification_payload
        gamification = gamification_payload(
            dict(user_row.profile or {}) if user_row else {},
            streak.get("today_date") or "",
        )
    except Exception:
        gamification = None
    return {
        "schedules": schedules,
        "schedule_streak": streak,
        "today_date": streak.get("today_date"),
        "day_number": streak.get("day_number"),
        "journey_start_date": streak.get("journey_start_date"),
        "newly_earned_achievements": newly_earned,
        "gamification": gamification,
    }


@router.get("/master")
async def get_master_schedule(
    days: int = 14,
    today: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Date-anchored master view across every active max.

    Returns a flat per-day list where each day's tasks come from any
    active max (skin/hair/height/etc.), already deconflicted by the
    multi-module collision pass:
        [
          {"date": "2026-05-04", "weekday": "Monday", "is_today": true,
           "task_count": 7,
           "tasks": [{maxx_id, catalog_id, title, time, ...}]},
          ...
        ]

    Updates automatically as maxes are added (new generation appends to
    the bucket) or removed (deactivated rows are filtered out by
    is_active=true). Cheap: no LLM, no RAG — just SQL + the in-process
    collision pass.
    """
    from services.master_schedule import build_master_view
    days = max(1, min(60, int(days)))
    out = await build_master_view(
        user_id=current_user["id"],
        db=db,
        days=days,
        today_iso=today,
    )
    return {"days": out, "window_days": days}


@router.post("/admin/guides/backfill")
async def backfill_task_guides(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: warm the task_guides cache for all active schedules in the background."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    rows = await db.execute(
        text("SELECT id, user_id FROM user_schedules WHERE status = 'active'")
    )
    schedules = rows.fetchall()
    for sid, uid in schedules:
        background_tasks.add_task(pregenerate_for_schedule, str(sid), str(uid))
    return {"queued": len(schedules)}


@router.get("/{schedule_id}")
async def get_schedule(
    schedule_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific schedule by ID"""
    schedule = await schedule_service.get_schedule_by_id(schedule_id, current_user["id"], db=db)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"schedule": schedule}


@router.put("/{schedule_id}/tasks/{task_id}/complete")
async def complete_task(
    schedule_id: str,
    task_id: str,
    data: CompleteTaskRequest = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a scheduled task as completed"""
    try:
        result = await schedule_service.complete_task(
            user_id=current_user["id"],
            schedule_id=schedule_id,
            task_id=task_id,
            db=db,
            feedback=data.feedback if data else None,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{schedule_id}/tasks/{task_id}/pending")
async def uncomplete_task(
    schedule_id: str,
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a completed task as pending again (toggle off)."""
    try:
        result = await schedule_service.uncomplete_task(
            user_id=current_user["id"],
            schedule_id=schedule_id,
            task_id=task_id,
            db=db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{schedule_id}/tasks/{task_id}")
async def edit_task(
    schedule_id: str,
    task_id: str,
    data: EditTaskRequest,
    scope: str = "instance",
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit a scheduled task (change time, title, description, duration).

    scope="instance" (default) edits the single tapped occurrence;
    scope="series" applies the change to the recurring part across every day
    and (for a time change) durably re-pins it through future re-expansions.
    """
    try:
        result = await schedule_service.edit_task(
            user_id=current_user["id"],
            schedule_id=schedule_id,
            task_id=task_id,
            db=db,
            updates=data.model_dump(exclude_none=True),
            scope=scope,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{schedule_id}/tasks/{task_id}")
async def delete_task(
    schedule_id: str,
    task_id: str,
    scope: str = "instance",
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task from the schedule.

    scope="instance" (default) removes the single tapped occurrence;
    scope="series" removes the whole recurring part across every day and
    keeps it from coming back on re-expansion.
    """
    try:
        result = await schedule_service.delete_task(
            user_id=current_user["id"],
            schedule_id=schedule_id,
            task_id=task_id,
            db=db,
            scope=scope,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class HabitPrefsRequest(BaseModel):
    wanted_catalog_ids: list[str] = []
    avoided_catalog_ids: list[str] = []


@router.get("/{schedule_id}/habit-options")
async def get_habit_options(
    schedule_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The tune-later picker's offered set for ONE schedule: the distinct catalog
    tasks actually on it (id/label/area) + the user's current wanted/avoided so
    the chips prefill to match reality. Drives the My-Maxxes tune sheet."""
    try:
        return await schedule_service.get_habit_options(
            user_id=current_user["id"], schedule_id=schedule_id, db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{schedule_id}/habit-prefs")
async def set_habit_prefs(
    schedule_id: str,
    data: HabitPrefsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply the chat habit-picker's want/avoid choices to one max's schedule.

    Persists the picks into schedule_context, then re-expands just this max so
    avoided habits are dropped and wanted ones are ensured present.
    """
    try:
        res = await schedule_service.set_habit_prefs(
            user_id=current_user["id"],
            schedule_id=schedule_id,
            db=db,
            wanted_catalog_ids=data.wanted_catalog_ids,
            avoided_catalog_ids=data.avoided_catalog_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Apply immediately by re-expanding only this max with the new prefs.
    # A regen failure must not lose the saved prefs (they apply on the next
    # context change either way), so swallow + log rather than 500.
    try:
        from services.schedule_runtime import regenerate_active_schedules
        await regenerate_active_schedules(
            user_id=current_user["id"], db=db, only_max=res["maxx_id"], reason="habit_prefs",
        )
        # regenerate_active_schedules only flushes; the caller owns the commit
        # (see every caller in api/users.py). Without this the re-expanded days
        # (avoided tasks dropped) get rolled back on session close — the prefs
        # persist but the plan still shows the deselected tasks.
        await db.commit()
    except Exception as e:
        await db.rollback()
        logging.getLogger(__name__).warning("habit-prefs regen failed (saved anyway): %s", e)

    schedule = await schedule_service.get_maxx_schedule(current_user["id"], res["maxx_id"], db=db)
    return {"status": "ok", "schedule": schedule, "wanted": res["wanted"], "avoided": res["avoided"]}


@router.put("/preferences")
async def update_preferences(
    prefs: SchedulePreferences,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update schedule notification/time preferences"""
    result = await schedule_service.update_preferences(
        current_user["id"], prefs.model_dump(), db=db
    )
    return result


@router.post("/{schedule_id}/adapt")
async def adapt_schedule(
    schedule_id: str,
    data: AdaptScheduleRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask AI to adapt the schedule based on feedback"""
    try:
        schedule = await schedule_service.adapt_schedule(
            user_id=current_user["id"],
            schedule_id=schedule_id,
            db=db,
            feedback=data.feedback,
        )
        background_tasks.add_task(
            pregenerate_for_schedule,
            schedule_id,
            str(current_user["id"]),
        )
        return {"schedule": schedule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{schedule_id}/tasks/{task_id}/guide")
async def get_task_guide_endpoint(
    schedule_id: str,
    task_id: str,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a step-by-step how-to guide for a specific schedule task.
    Generated once via LLM (grounded on maxx protocols) and cached indefinitely.
    """
    try:
        guide = await get_task_guide(
            schedule_id=schedule_id,
            task_id=task_id,
            user_id=current_user["id"],
            db=db,
        )
        return guide
    except Exception as e:
        logging.getLogger(__name__).exception("get_task_guide failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate task guide")


@router.post("/{schedule_id}/stop")
async def stop_schedule(
    schedule_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate/stop a schedule."""
    try:
        result = await schedule_service.deactivate_schedule(
            user_id=current_user["id"],
            schedule_id=schedule_id,
            db=db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

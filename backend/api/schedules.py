"""
Schedules API - AI-powered personalised schedules for course modules
"""

from fastapi import APIRouter, HTTPException, Depends
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
from middleware.auth_middleware import require_paid_user
from services.schedule_service import schedule_service

router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.post("/generate")
async def generate_schedule(
    data: GenerateScheduleRequest,
    current_user: dict = Depends(require_paid_user),
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
        )
        return {"schedule": schedule}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schedule generation failed: {e}")


@router.post("/generate-maxx")
async def generate_maxx_schedule(
    data: GenerateMaxxScheduleRequest,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Generate a personalised AI schedule for a maxx module (e.g. SkinMax)"""
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
        )
        return {"schedule": schedule}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Maxx schedule generation failed: {e}")


@router.get("/maxx/{maxx_id}")
async def get_maxx_schedule(
    maxx_id: str,
    current_user: dict = Depends(require_paid_user),
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
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's current active schedule, optionally filtered by course/module"""
    schedule = await schedule_service.get_current_schedule(
        current_user["id"], db=db, course_id=course_id, module_number=module_number
    )
    if not schedule:
        return {"schedule": None, "message": "No active schedule. Generate one from a course module."}
    return {"schedule": schedule}


@router.get("/{schedule_id}")
async def get_schedule(
    schedule_id: str,
    current_user: dict = Depends(require_paid_user),
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
    current_user: dict = Depends(require_paid_user),
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


@router.put("/{schedule_id}/tasks/{task_id}")
async def edit_task(
    schedule_id: str,
    task_id: str,
    data: EditTaskRequest,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit a scheduled task (change time, title, description, duration)"""
    try:
        result = await schedule_service.edit_task(
            user_id=current_user["id"],
            schedule_id=schedule_id,
            task_id=task_id,
            db=db,
            updates=data.model_dump(exclude_none=True),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{schedule_id}/tasks/{task_id}")
async def delete_task(
    schedule_id: str,
    task_id: str,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task from the schedule"""
    try:
        result = await schedule_service.delete_task(
            user_id=current_user["id"],
            schedule_id=schedule_id,
            task_id=task_id,
            db=db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/preferences")
async def update_preferences(
    prefs: SchedulePreferences,
    current_user: dict = Depends(require_paid_user),
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
    current_user: dict = Depends(require_paid_user),
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
        return {"schedule": schedule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

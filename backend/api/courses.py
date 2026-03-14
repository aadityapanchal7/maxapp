"""
Courses API
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db, get_rds_db
from middleware.auth_middleware import require_paid_user, get_current_admin_user
from models.course import CourseCreate, CourseResponse, ChapterCompletionRequest
from models.rds_models import Course
from models.sqlalchemy_models import UserCourseProgress

router = APIRouter(prefix="/courses", tags=["Courses"])


@router.get("")
async def list_courses(
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """List all active courses"""
    result = await rds_db.execute(select(Course).where(Course.is_active == True))
    courses = result.scalars().all()
    return {"courses": [
        {
            "id": str(c.id),
            "title": c.title,
            "description": c.description,
            "category": c.category,
            "thumbnail_url": c.thumbnail_url,
            "difficulty": c.difficulty,
            "estimated_weeks": c.estimated_weeks,
            "modules": c.modules or [],
            "total_chapters": sum(len(m.get("chapters", [])) for m in (c.modules or [])),
            "is_active": c.is_active,
            "created_at": c.created_at
        }
        for c in courses
    ]}


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: str,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Get course details"""
    try:
        course_uuid = UUID(course_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid course ID format")

    result = await rds_db.execute(select(Course).where(Course.id == course_uuid))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return {
        "id": str(course.id),
        "title": course.title,
        "description": course.description,
        "category": course.category,
        "thumbnail_url": course.thumbnail_url,
        "difficulty": course.difficulty,
        "estimated_weeks": course.estimated_weeks,
        "modules": course.modules or [],
        "total_chapters": sum(len(m.get("chapters", [])) for m in (course.modules or [])),
        "is_active": course.is_active,
        "created_at": course.created_at
    }


@router.post("/{course_id}/start")
async def start_course(
    course_id: str,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db)
):
    """Start a course"""
    try:
        course_uuid = UUID(course_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid course ID format")

    result = await rds_db.execute(select(Course).where(Course.id == course_uuid))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    existing_result = await db.execute(
        select(UserCourseProgress).where(
            (UserCourseProgress.user_id == UUID(current_user["id"])) &
            (UserCourseProgress.course_id == course_uuid)
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return {"message": "Already enrolled", "progress_id": str(existing.id)}
    
    progress = UserCourseProgress(
        user_id=UUID(current_user["id"]),
        course_id=course_uuid,
        course_title=course.title,
        current_module=1,
        completed_chapters=[],
        progress_percentage=0.0,
        started_at=datetime.utcnow(),
        last_activity=datetime.utcnow(),
        is_completed=False
    )
    db.add(progress)
    await db.commit()
    await db.refresh(progress)
    return {"message": "Course started", "progress_id": str(progress.id)}


@router.put("/{course_id}/complete-chapter")
async def complete_chapter(
    course_id: str,
    data: ChapterCompletionRequest,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
    db: AsyncSession = Depends(get_db),
):
    """Mark chapter as complete"""
    try:
        course_uuid = UUID(course_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid course ID format")

    result = await db.execute(
        select(UserCourseProgress).where(
            (UserCourseProgress.user_id == UUID(current_user["id"])) &
            (UserCourseProgress.course_id == course_uuid)
        )
    )
    progress = result.scalar_one_or_none()
    if not progress:
        raise HTTPException(status_code=404, detail="Not enrolled in course")
    
    completed = progress.completed_chapters or []
    if data.chapter_id not in completed:
        completed.append(data.chapter_id)
    
    course_result = await rds_db.execute(select(Course).where(Course.id == course_uuid))
    course = course_result.scalar_one_or_none()
    
    # Calculate progress
    total_chapters = sum(len(m.get("chapters", [])) for m in (course.modules or []))
    percentage = (len(completed) / total_chapters * 100) if total_chapters > 0 else 0
    
    # Update current module logic (simple: max module touched or just logic based on percentage)
    # For now, keep as is or update based on chapter's module
    
    progress.completed_chapters = completed
    progress.progress_percentage = percentage
    progress.last_activity = datetime.utcnow()
    progress.current_module = data.module_number
    await db.commit()
    return {"progress_percentage": percentage}


@router.get("/progress/current")
async def get_current_progress(
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's course progress"""
    result = await db.execute(
        select(UserCourseProgress).where(UserCourseProgress.user_id == UUID(current_user["id"]))
    )
    progress_list = result.scalars().all()
    progress = [
        {
            "id": str(p.id),
            "course_id": str(p.course_id),
            "course_title": p.course_title or "Course",
            "progress_percentage": p.progress_percentage,
            "completed_chapters": p.completed_chapters or [],
            "current_module": p.current_module or 1
        }
        for p in progress_list
    ]
    return {"progress": progress}


@router.post("")
async def create_course(
    data: CourseCreate,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Create course (admin only)"""
    course = Course(
        title=data.title,
        description=data.description,
        category=data.category.value if hasattr(data.category, "value") else data.category,
        thumbnail_url=data.thumbnail_url,
        difficulty=data.difficulty,
        estimated_weeks=data.estimated_weeks,
        modules=[m.model_dump() for m in data.modules],
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    rds_db.add(course)
    await rds_db.commit()
    await rds_db.refresh(course)
    return {"course_id": str(course.id)}

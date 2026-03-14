"""
Courses API
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime

from db import get_rds_db
from middleware.auth_middleware import require_paid_user, get_current_admin_user
from models.rds_models import Course, Lesson
from models.sqlalchemy_models import UserCourseProgress
from db import get_db

router = APIRouter(prefix="/courses", tags=["Courses"])


@router.get("")
async def list_courses(
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """List all active courses"""
    result = await rds_db.execute(select(Course).where(Course.is_published == True))
    courses = result.scalars().all()
    return {"courses": [
        {
            "id": str(course.id),
            "title": course.title,
            "description": course.description,
            "level": course.level,
            "duration_minutes": course.duration_minutes,
            "price": str(course.price) if course.price else None,
            "created_at": course.created_at
        }
        for course in courses
    ]}


@router.get("/{course_id}")
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

    # Get lessons for this course
    lessons_result = await rds_db.execute(select(Lesson).where(Lesson.course_id == course_uuid).order_by(Lesson.order))
    lessons = lessons_result.scalars().all()

    return {
        "id": str(course.id),
        "title": course.title,
        "description": course.description,
        "level": course.level,
        "duration_minutes": course.duration_minutes,
        "price": str(course.price) if course.price else None,
        "is_published": course.is_published,
        "lessons": [
            {
                "id": str(lesson.id),
                "title": lesson.title,
                "description": lesson.description,
                "order": lesson.order,
                "duration_minutes": lesson.duration_minutes
            }
            for lesson in lessons
        ]
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

    user_uuid = UUID(current_user["id"])

    # Check if already enrolled
    existing_result = await db.execute(
        select(UserCourseProgress).where(
            (UserCourseProgress.user_id == user_uuid) &
            (UserCourseProgress.course_id == course_uuid)
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        return {"message": "Already enrolled", "progress_id": str(existing.id)}

    # Create new enrollment
    progress = UserCourseProgress(
        user_id=user_uuid,
        course_id=course_uuid,
        enrollment_date=datetime.utcnow(),
        current_module=0,
        is_completed=False
    )

    db.add(progress)
    await db.commit()
    await db.refresh(progress)

    return {"message": "Course started", "progress_id": str(progress.id)}


@router.put("/{course_id}/complete-chapter")
async def complete_chapter(
    course_id: str,
    data: dict = None,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark chapter as complete"""
    try:
        course_uuid = UUID(course_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid course ID format")

    user_uuid = UUID(current_user["id"])

    # Find user's course progress
    result = await db.execute(
        select(UserCourseProgress).where(
            (UserCourseProgress.user_id == user_uuid) &
            (UserCourseProgress.course_id == course_uuid)
        )
    )
    progress = result.scalar_one_or_none()

    if not progress:
        raise HTTPException(status_code=404, detail="Not enrolled in course")

    if data is None:
        data = {}

    chapter_id = data.get("chapter_id")
    module_number = data.get("module_number", 0)

    # Update completed chapters
    completed = progress.completed_chapters or []
    if chapter_id and chapter_id not in completed:
        completed.append(chapter_id)

    progress.completed_chapters = completed
    progress.current_module = module_number
    progress.updated_at = datetime.utcnow()

    await db.commit()

    return {"progress_percentage": 0}  # Simplified for now


@router.get("/progress/current")
async def get_current_progress(
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's course progress"""
    user_uuid = UUID(current_user["id"])

    result = await db.execute(
        select(UserCourseProgress).where(UserCourseProgress.user_id == user_uuid)
    )
    progress_list = result.scalars().all()

    return {"progress": [
        {
            "id": str(p.id),
            "course_id": str(p.course_id),
            "current_module": p.current_module,
            "is_completed": p.is_completed,
            "completed_chapters": p.completed_chapters or [],
            "enrollment_date": p.enrollment_date
        }
        for p in progress_list
    ]}


@router.post("")
async def create_course(
    data: dict = None,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Create course (admin only)"""
    if data is None:
        data = {}

    course = Course(
        title=data.get("title"),
        description=data.get("description"),
        level=data.get("level"),
        duration_minutes=data.get("duration_minutes"),
        price=data.get("price"),
        is_published=False
    )

    rds_db.add(course)
    await rds_db.commit()
    await rds_db.refresh(course)

    return {"course_id": str(course.id)}

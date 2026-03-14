"""
Leaderboard API
"""

from fastapi import APIRouter, Depends
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from middleware.auth_middleware import require_paid_user
from models.sqlalchemy_models import Leaderboard, User, Scan

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


@router.get("")
async def get_leaderboard(
    limit: int = 100,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Get leaderboard rankings"""
    result = await db.execute(
        select(Leaderboard).order_by(Leaderboard.rank).limit(limit)
    )
    entries = []
    for entry in result.scalars().all():
        user = await db.get(User, entry.user_id)
        if user and user.is_admin:
            continue
        entries.append({
            "rank": entry.rank or 0,
            "user_id": str(entry.user_id),
            "user_email": user.email[:3] + "***" if user else "Anonymous",
            "score": entry.score or 0,
            "level": entry.level or 0,
            "streak_days": entry.streak_days or 0,
            "improvement_percentage": entry.improvement_percentage or 0
        })
    total = len(entries)
    return {"entries": entries, "total_users": total}


@router.get("/me")
async def get_my_rank(
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's rank"""
    if current_user.get("is_admin"):
        return {"rank": None, "total_users": 0, "message": "Admins are excluded from leaderboard"}

    user_id = current_user["id"]
    user_uuid = UUID(user_id)
    result = await db.execute(select(Leaderboard).where(Leaderboard.user_id == user_uuid))
    entry = result.scalar_one_or_none()
    total_result = await db.execute(select(Leaderboard))
    total = len(total_result.scalars().all())
    
    # If no leaderboard entry, check if user has completed scans and create entry
    if not entry:
        latest_scan_result = await db.execute(
            select(Scan)
            .where((Scan.user_id == user_uuid) & (Scan.processing_status == "completed"))
            .order_by(Scan.created_at.desc())
            .limit(1)
        )
        latest_scan = latest_scan_result.scalar_one_or_none()
        
        if latest_scan:
            # User has completed scan but no leaderboard entry - create one
            analysis = latest_scan.analysis or {}
            overall_score = analysis.get("overall_score") or analysis.get("metrics", {}).get("overall_score", 0)
            leaderboard_score = (float(overall_score) if overall_score else 0) * 10
            
            # Count scans
            scans_result = await db.execute(
                select(Scan).where(
                    (Scan.user_id == user_uuid) & (Scan.processing_status == "completed")
                )
            )
            scans_count = len(scans_result.scalars().all())
            
            # Create leaderboard entry
            new_entry = Leaderboard(
                user_id=user_uuid,
                score=leaderboard_score,
                level=float(overall_score) if overall_score else 0,
                streak_days=1,
                improvement_percentage=0,
                scans_count=scans_count,
                last_scan_at=latest_scan.created_at or datetime.utcnow(),
                created_at=datetime.utcnow()
            )
            db.add(new_entry)
            await db.commit()
            
            # Recalculate all ranks
            all_entries_result = await db.execute(
                select(Leaderboard).order_by(Leaderboard.score.desc())
            )
            all_entries = all_entries_result.scalars().all()
            for rank, e in enumerate(all_entries, 1):
                e.rank = rank
            await db.commit()
            
            # Fetch the newly created entry with rank
            result = await db.execute(select(Leaderboard).where(Leaderboard.user_id == user_uuid))
            entry = result.scalar_one_or_none()
            total_result = await db.execute(select(Leaderboard))
            total = len(total_result.scalars().all())
        else:
            return {"rank": None, "total_users": total, "message": "Complete a scan to join"}
    
    return {
        "rank": entry.rank or 0,
        "total_users": total,
        "score": entry.score or 0,
        "level": entry.level or 0,
        "streak_days": entry.streak_days or 0,
        "improvement_percentage": entry.improvement_percentage or 0
    }


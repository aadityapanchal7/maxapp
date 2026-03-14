"""
Events API - TikTok Live events
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_rds_db
from middleware.auth_middleware import require_paid_user, get_current_admin_user
from models.event import EventCreate
from models.rds_models import Event

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("")
async def list_events(
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """List upcoming events"""
    result = await rds_db.execute(
        select(Event).where(Event.scheduled_at >= datetime.utcnow()).order_by(Event.scheduled_at).limit(20)
    )
    events = result.scalars().all()
    return {"events": [
        {
            "id": str(e.id),
            "title": e.title,
            "description": e.description,
            "scheduled_at": e.scheduled_at,
            "duration_minutes": e.duration_minutes,
            "tiktok_link": e.tiktok_link,
            "thumbnail_url": e.thumbnail_url,
            "is_live": e.is_live,
            "is_past": False
        }
        for e in events
    ]}


@router.get("/live")
async def get_live_events(
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Get currently live events"""
    result = await rds_db.execute(select(Event).where(Event.is_live == True))
    events = result.scalars().all()
    return {"events": [
        {"id": str(e.id), "title": e.title, "tiktok_link": e.tiktok_link}
        for e in events
    ]}


@router.get("/calendar")
async def get_calendar(
    month: int = None,
    year: int = None,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Get events for calendar view"""
    now = datetime.utcnow()
    month = month or now.month
    year = year or now.year
    
    start = datetime(year, month, 1)
    end = datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)
    
    result = await rds_db.execute(
        select(Event).where((Event.scheduled_at >= start) & (Event.scheduled_at < end)).order_by(Event.scheduled_at)
    )
    events = result.scalars().all()
    return {
        "events": [
            {
                "id": str(e.id),
                "title": e.title,
                "scheduled_at": e.scheduled_at,
                "duration_minutes": e.duration_minutes or 60,
                "thumbnail_url": e.thumbnail_url
            }
            for e in events
        ],
        "month": month,
        "year": year
    }


@router.post("")
async def create_event(
    data: EventCreate,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Create event (admin only)"""
    event = Event(
        title=data.title,
        description=data.description,
        scheduled_at=data.scheduled_at,
        duration_minutes=data.duration_minutes,
        tiktok_link=data.tiktok_link,
        thumbnail_url=data.thumbnail_url,
        is_live=False,
        created_at=datetime.utcnow(),
    )
    rds_db.add(event)
    await rds_db.commit()
    await rds_db.refresh(event)
    return {"event_id": str(event.id)}

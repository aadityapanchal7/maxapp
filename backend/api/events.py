"""
Events API - Community events and challenges
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime

from db import get_rds_db
from middleware.auth_middleware import require_paid_user, get_current_admin_user
from models.rds_models import Event, EventRegistration

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("")
async def list_events(
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """List upcoming events"""
    now = datetime.utcnow()
    result = await rds_db.execute(
        select(Event)
        .where((Event.start_date >= now) & (Event.is_active == True))
        .order_by(Event.start_date)
        .limit(20)
    )
    events = result.scalars().all()

    return {"events": [
        {
            "id": str(event.id),
            "title": event.title,
            "description": event.description,
            "type": event.type,
            "start_date": event.start_date,
            "end_date": event.end_date,
            "location": event.location,
            "capacity": event.capacity,
            "is_active": event.is_active
        }
        for event in events
    ]}


@router.get("/live")
async def get_live_events(
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Get currently live events"""
    now = datetime.utcnow()
    result = await rds_db.execute(
        select(Event).where(
            (Event.start_date <= now) &
            ((Event.end_date >= now) | (Event.end_date.is_(None))) &
            (Event.is_active == True)
        )
    )
    events = result.scalars().all()

    return {"events": [
        {
            "id": str(event.id),
            "title": event.title,
            "location": event.location
        }
        for event in events
    ]}


@router.get("/calendar")
async def get_calendar(
    month: int = None,
    year: int = None,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Get events for calendar view"""
    now = datetime.utcnow()
    month = month or now.month
    year = year or now.year

    start = datetime(year, month, 1)
    end = datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)

    result = await rds_db.execute(
        select(Event)
        .where((Event.start_date >= start) & (Event.start_date < end))
        .order_by(Event.start_date)
    )
    events = result.scalars().all()

    return {"events": [
        {
            "id": str(event.id),
            "title": event.title,
            "start_date": event.start_date,
            "duration_minutes": 60  # Default duration if not specified
        }
        for event in events
    ], "month": month, "year": year}


@router.get("/{event_id}")
async def get_event(
    event_id: str,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Get event details"""
    try:
        event_uuid = UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID format")

    result = await rds_db.execute(select(Event).where(Event.id == event_uuid))
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Get registration count
    registrations_result = await rds_db.execute(
        select(EventRegistration).where(EventRegistration.event_id == event_uuid)
    )
    registrations = registrations_result.scalars().all()

    user_registered = any(r.user_id == UUID(current_user["id"]) for r in registrations)

    return {
        "id": str(event.id),
        "title": event.title,
        "description": event.description,
        "type": event.type,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "location": event.location,
        "capacity": event.capacity,
        "is_active": event.is_active,
        "registration_count": len(registrations),
        "user_registered": user_registered
    }


@router.post("/{event_id}/register")
async def register_for_event(
    event_id: str,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Register for an event"""
    try:
        event_uuid = UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID format")

    user_uuid = UUID(current_user["id"])

    # Verify event exists
    event_result = await rds_db.execute(select(Event).where(Event.id == event_uuid))
    event = event_result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if not event.is_active:
        raise HTTPException(status_code=400, detail="Event is not active")

    # Check if already registered
    existing_result = await rds_db.execute(
        select(EventRegistration).where(
            (EventRegistration.event_id == event_uuid) &
            (EventRegistration.user_id == user_uuid)
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already registered for this event")

    # Check capacity
    if event.capacity:
        registrations_result = await rds_db.execute(
            select(EventRegistration).where(EventRegistration.event_id == event_uuid)
        )
        if len(registrations_result.scalars().all()) >= event.capacity:
            raise HTTPException(status_code=400, detail="Event is at capacity")

    # Create registration
    registration = EventRegistration(
        event_id=event_uuid,
        user_id=user_uuid,
        status="registered"
    )

    rds_db.add(registration)
    await rds_db.commit()
    await rds_db.refresh(registration)

    return {"registration_id": str(registration.id), "status": "registered"}


@router.post("/{event_id}/unregister")
async def unregister_from_event(
    event_id: str,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Unregister from an event"""
    try:
        event_uuid = UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID format")

    user_uuid = UUID(current_user["id"])

    # Find registration
    result = await rds_db.execute(
        select(EventRegistration).where(
            (EventRegistration.event_id == event_uuid) &
            (EventRegistration.user_id == user_uuid)
        )
    )
    registration = result.scalar_one_or_none()

    if not registration:
        raise HTTPException(status_code=404, detail="Not registered for this event")

    await rds_db.delete(registration)
    await rds_db.commit()

    return {"status": "unregistered"}


@router.post("")
async def create_event(
    data: dict = None,
    admin: dict = Depends(get_current_admin_user),
    rds_db: AsyncSession = Depends(get_rds_db)
):
    """Create event (admin only)"""
    if data is None:
        data = {}

    event = Event(
        title=data.get("title"),
        description=data.get("description"),
        type=data.get("type"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        location=data.get("location"),
        capacity=data.get("capacity"),
        is_active=True
    )

    rds_db.add(event)
    await rds_db.commit()
    await rds_db.refresh(event)

    return {"event_id": str(event.id)}

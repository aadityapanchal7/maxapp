"""LLM-triggered push notification queue.

The chat pipeline writes rows via `enqueue_push`; a worker job (bonemax scheduler
or a dedicated poller) should select pending rows where scheduled_for <= now and
dispatch them via the existing APNs service.

A minimal dispatcher (`dispatch_due`) is included so you can wire it into the
existing APScheduler loop without building a new service.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import ScheduledNotification, User

logger = logging.getLogger(__name__)


async def enqueue_push(
    *,
    db: AsyncSession,
    user_id: str,
    delay_minutes: int,
    message: str,
    buttons: Optional[List[str]] = None,
    category_id: str = "coach_nudge",
) -> int:
    """Insert a pending row. Returns the new notification id."""
    if buttons:
        buttons = [b for b in buttons if isinstance(b, str) and b.strip()][:2] or None
    scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=max(1, int(delay_minutes)))
    row = ScheduledNotification(
        user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
        scheduled_for=scheduled_for,
        message=message.strip()[:240],
        buttons=buttons,
        category_id=category_id,
        status="pending",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return int(row.id)


async def dispatch_due(db: AsyncSession) -> int:
    """Send every pending push whose scheduled_for has passed. Returns send count.

    Called from the existing scheduler loop (e.g. in services/scheduler_job.py).
    Uses the existing APNs service; no-ops cleanly if that service isn't present.
    """
    now = datetime.now(timezone.utc)
    q = (
        select(ScheduledNotification)
        .where(ScheduledNotification.status == "pending")
        .where(ScheduledNotification.scheduled_for <= now)
        .order_by(ScheduledNotification.scheduled_for.asc())
        .limit(50)
    )
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return 0

    try:
        from services.apns_service import send_push  # type: ignore
    except ImportError:
        try:
            from services.push_service import send_push  # type: ignore
        except ImportError:
            logger.warning("No APNs service found; cannot dispatch %d pushes", len(rows))
            return 0

    sent = 0
    for row in rows:
        user = await db.get(User, row.user_id)
        token = getattr(user, "apns_device_token", None) if user else None
        if not token:
            await db.execute(
                update(ScheduledNotification)
                .where(ScheduledNotification.id == row.id)
                .values(status="failed", sent_at=datetime.now(timezone.utc))
            )
            continue
        try:
            await send_push(
                token=token,
                body=row.message,
                category=row.category_id,
                # Existing send_push may accept a `buttons` kwarg; if not, the push still fires.
                # Registering the APNs category at app launch maps buttons to actions.
                data={"buttons": row.buttons or []},
            )
            await db.execute(
                update(ScheduledNotification)
                .where(ScheduledNotification.id == row.id)
                .values(status="sent", sent_at=datetime.now(timezone.utc))
            )
            sent += 1
        except Exception as e:
            logger.warning("push send failed for notification %s: %s", row.id, e)
            await db.execute(
                update(ScheduledNotification)
                .where(ScheduledNotification.id == row.id)
                .values(status="failed", sent_at=datetime.now(timezone.utc))
            )
    await db.commit()
    return sent

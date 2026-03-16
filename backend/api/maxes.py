"""
Maxes API - Looksmaxxing programs (fitmax, skinmax, etc.)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_rds_db
from middleware.auth_middleware import require_paid_user
from models.rds_models import Maxx

router = APIRouter(prefix="/maxes", tags=["Maxes"])


@router.get("")
async def list_maxes(
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Return all active maxxes"""
    result = await rds_db.execute(select(Maxx).where(Maxx.is_active == True))
    maxes = result.scalars().all()
    return {"maxes": [_serialize(m) for m in maxes]}


@router.get("/{maxx_id}")
async def get_maxx(
    maxx_id: str,
    current_user: dict = Depends(require_paid_user),
    rds_db: AsyncSession = Depends(get_rds_db),
):
    """Return a single maxx by id (e.g. 'fitmax')"""
    result = await rds_db.execute(select(Maxx).where(Maxx.id == maxx_id))
    maxx = result.scalar_one_or_none()
    if not maxx:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Maxx not found")
    return _serialize(maxx)


def _serialize(m: Maxx) -> dict:
    return {
        "id": m.id,
        "label": m.label,
        "description": m.description,
        "icon": m.icon,
        "color": m.color,
        "modules": m.modules or [],
        "protocols": m.protocols or {},
        "concerns": m.concerns or [],
        "concern_question": m.concern_question,
        "is_active": m.is_active,
        "created_at": m.created_at,
    }

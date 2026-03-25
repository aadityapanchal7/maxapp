"""
Sendblue receive webhook — inbound iMessage/SMS routes through Max AI; images save as progress photos.
Reply is sent via Sendblue outbound API (not TwiML).
"""

import logging
from collections import OrderedDict

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from db import get_db, get_rds_db_optional
from models.sqlalchemy_models import User
from services.sendblue_service import phone_lookup_candidates, sendblue_service
from services.sms_mms_ingest import ingest_sendblue_media_progress_photo
from api.chat import process_chat_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sendblue", tags=["Sendblue Webhook"])

# Best-effort dedupe (multi-worker: use Redis in production if needed)
_MAX_HANDLES = 4000
_seen_handles: OrderedDict[str, bool] = OrderedDict()


def _seen_message(handle: str | None) -> bool:
    if not handle:
        return False
    if handle in _seen_handles:
        return True
    _seen_handles[handle] = True
    _seen_handles.move_to_end(handle)
    while len(_seen_handles) > _MAX_HANDLES:
        _seen_handles.popitem(last=False)
    return False


@router.post("/receive")
async def sendblue_receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession | None = Depends(get_rds_db_optional),
):
    """
    Configure in Sendblue dashboard (receive webhook): POST https://<api>/api/sendblue/receive
    """
    if settings.sendblue_webhook_secret:
        secret = (
            request.headers.get("sb-webhook-secret")
            or request.headers.get("SB-Webhook-Secret")
            or request.headers.get("x-sendblue-secret")
            or ""
        )
        if secret != settings.sendblue_webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Expected JSON body")

    if payload.get("is_outbound") is True:
        return {"ok": True, "ignored": "outbound"}

    handle = payload.get("message_handle")
    if _seen_message(str(handle) if handle else ""):
        return {"ok": True, "duplicate": True}

    raw_number = str(payload.get("number") or payload.get("from_number") or "").strip()
    body = str(payload.get("content") or "").strip()
    media_url = str(payload.get("media_url") or "").strip()

    if not raw_number:
        return {"ok": True}

    candidates = phone_lookup_candidates(raw_number)
    logger.info(
        "Sendblue inbound number=%s candidates=%s body_len=%s has_media=%s",
        raw_number,
        candidates,
        len(body),
        bool(media_url),
    )

    result = await db.execute(select(User).where(User.phone_number.in_(candidates)).limit(1))
    user = result.scalars().first()

    if not user:
        await sendblue_service.send_message(
            raw_number,
            "hey — you're not on max yet. sign up in the app to get started: https://maxmaxmax.today",
        )
        return {"ok": True}

    user_id_str = str(user.id)
    parts: list[str] = []
    mms_stored = 0

    if media_url:
        try:
            mms_stored = await ingest_sendblue_media_progress_photo(db, user, media_url)
            if mms_stored > 0:
                parts.append(
                    f"got {'those pics' if mms_stored > 1 else 'it'} — saved to your progress archive in the app."
                )
            await db.commit()
        except Exception as e:
            logger.error("Sendblue media ingest failed for user %s: %s", user_id_str, e, exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass
            parts.append("couldn't save the image that time — try again or upload from the app.")
        if mms_stored == 0 and not parts:
            parts.append("couldn't read that image — try again or upload from the app.")

    if not body and not parts:
        return {"ok": True}

    response_text = ""
    if body:
        try:
            response_text = await process_chat_message(
                user_id=user_id_str,
                message_text=body,
                db=db,
                rds_db=rds_db,
                channel="sms",
            )
        except Exception as e:
            logger.error("Sendblue chat failed for user %s: %s", user_id_str, e, exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass
            if rds_db is not None:
                try:
                    await rds_db.rollback()
                except Exception:
                    pass
            response_text = "my bad, hit a snag. try again."
        if not (response_text or "").strip():
            response_text = "got it. open the app if you need more detail."

    combined = " ".join(p for p in [*parts, response_text.strip()] if p).strip()
    if not combined:
        combined = "got it."
    if len(combined) > 1550:
        combined = combined[:1547] + "..."

    await sendblue_service.send_message(raw_number, combined)
    return {"ok": True}

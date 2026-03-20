"""
Twilio SMS/MMS Webhook — Incoming SMS routes through Max AI; MMS images save as progress pictures.
"""

import logging
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db import get_db, get_rds_db_optional
from models.sqlalchemy_models import User
from services.twilio_service import phone_lookup_candidates
from services.sms_mms_ingest import ingest_mms_progress_photos_from_form
from api.chat import process_chat_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio", tags=["Twilio Webhook"])

TWIML_EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _twiml_reply(text: str) -> str:
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>'


@router.post("/sms")
async def sms_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    rds_db: AsyncSession | None = Depends(get_rds_db_optional),
):
    """
    Twilio calls this for inbound SMS and MMS.
    - MMS with image(s): each image is stored as a progress picture (S3/local) for the matched user.
    - Text (with or without prior images): runs Max chat when Body is non-empty.
    """
    form = await request.form()
    from_phone = str(form.get("From", ""))
    body = str(form.get("Body", "")).strip()

    try:
        num_media = int(form.get("NumMedia") or 0)
    except (TypeError, ValueError):
        num_media = 0

    if not from_phone:
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    candidates = phone_lookup_candidates(from_phone)
    logger.info(
        "Twilio inbound from=%s candidates=%s body_len=%s num_media=%s",
        from_phone,
        candidates,
        len(body),
        num_media,
    )

    result = await db.execute(
        select(User).where(User.phone_number.in_(candidates)).limit(1)
    )
    user = result.scalars().first()

    if not user:
        reply = "hey, you're not signed up for max yet. download the app to get started."
        return Response(content=_twiml_reply(reply), media_type="application/xml")

    user_id_str = str(user.id)

    parts: list[str] = []
    mms_stored = 0

    if num_media > 0:
        try:
            mms_stored = await ingest_mms_progress_photos_from_form(db, user, form)
            if mms_stored > 0:
                parts.append(
                    f"got {'those pics' if mms_stored > 1 else 'it'} — saved to your progress archive in the app."
                )
            await db.commit()
        except Exception as e:
            logger.error("MMS progress ingest failed for user %s: %s", user_id_str, e, exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass
            parts.append("couldn't save the image that time — try again or upload from the app.")
        if mms_stored == 0 and not parts:
            parts.append("couldn't read that image — try again or upload from the app.")

    if not body and not parts:
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    response_text = ""
    if body:
        try:
            response_text = await process_chat_message(
                user_id=user_id_str,
                message_text=body,
                db=db,
                rds_db=rds_db,
            )
        except Exception as e:
            logger.error("SMS chat processing failed for user %s: %s", user_id_str, e, exc_info=True)
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

    return Response(content=_twiml_reply(combined), media_type="application/xml")

"""
Twilio SMS Webhook — Receives incoming SMS messages and routes them through the Max AI chatbot.
Users can text the Twilio number and get AI replies via SMS.
"""

import logging
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db import get_db, get_rds_db_optional
from models.sqlalchemy_models import User
from services.twilio_service import phone_lookup_candidates
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
    Twilio calls this when an SMS arrives at our number.
    We look up the user by phone, run the message through Max AI, and reply via SMS.
    """
    form = await request.form()
    from_phone = str(form.get("From", ""))
    body = str(form.get("Body", "")).strip()

    if not from_phone or not body:
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    candidates = phone_lookup_candidates(from_phone)
    logger.info("Twilio SMS from=%s candidates=%s body_len=%s", from_phone, candidates, len(body))

    # Look up user by any common phone format
    result = await db.execute(
        select(User).where(User.phone_number.in_(candidates)).limit(1)
    )
    user = result.scalars().first()

    if not user:
        reply = "hey, you're not signed up for max yet. download the app to get started."
        return Response(content=_twiml_reply(reply), media_type="application/xml")

    # Snapshot before any long-running work — avoids lazy-load / expired ORM state in except blocks.
    user_id_str = str(user.id)

    # Do NOT wrap in asyncio.wait_for(): cancelling mid-request aborts DB commits (adapt_schedule etc.),
    # leaving the session in PendingRollbackError and breaking the next request.
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

    # Truncate to SMS limit (~1550 chars to leave room for encoding)
    if len(response_text) > 1550:
        response_text = response_text[:1547] + "..."

    return Response(content=_twiml_reply(response_text), media_type="application/xml")

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
from services.twilio_service import twilio_service, normalize_phone
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

    normalized = normalize_phone(from_phone)

    # Look up user by phone number
    result = await db.execute(select(User).where(User.phone_number == normalized))
    user = result.scalar_one_or_none()

    if not user:
        # Try without normalization in case stored format differs
        result = await db.execute(select(User).where(User.phone_number == from_phone))
        user = result.scalar_one_or_none()

    if not user:
        reply = "hey, you're not signed up for max yet. download the app to get started."
        return Response(content=_twiml_reply(reply), media_type="application/xml")

    try:
        response_text = await process_chat_message(
            user_id=str(user.id),
            message_text=body,
            db=db,
            rds_db=rds_db,
        )
    except Exception as e:
        logger.error(f"SMS chat processing failed for {user.id}: {e}", exc_info=True)
        response_text = "my bad, hit a snag. try again."

    # Truncate to SMS limit (~1550 chars to leave room for encoding)
    if len(response_text) > 1550:
        response_text = response_text[:1547] + "..."

    return Response(content=_twiml_reply(response_text), media_type="application/xml")

"""
Sendblue receive webhook — inbound iMessage/SMS routes through Max AI; images save as progress photos.
Reply is sent via Sendblue outbound API (not TwiML).

Sendblue requires a quick HTTP response to avoid duplicate webhook deliveries; AI + outbound send run in a background task.
"""

import logging
from collections import OrderedDict

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from config import settings
from db import AsyncSessionLocal
from db.rds import RDSSessionLocal
from models.sqlalchemy_models import User
from services.sendblue_service import phone_lookup_candidates, sendblue_service
from services.sms_mms_ingest import ingest_sendblue_media_progress_photo
from api.chat import process_chat_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sendblue", tags=["Sendblue Webhook"])

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


async def _sendblue_inbound_core(
    db,
    rds_db,
    raw_number: str,
    body: str,
    media_url: str,
) -> None:
    """DB + RDS sessions must be open; sends outbound SMS when appropriate."""
    candidates = phone_lookup_candidates(raw_number)
    logger.info(
        "Sendblue process number=%s candidates=%s body_len=%s has_media=%s",
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
            "hey — don't think i've got you on max yet. grab the app here if you want in: https://maxmaxmax.today",
        )
        return

    user_id_str = str(user.id)

    ob = dict(user.onboarding or {})
    first_thread_message = not ob.get("sendblue_sms_engaged")
    if first_thread_message:
        ob["sendblue_sms_engaged"] = True
        # sendblue_connect_completed is set only in-app after user taps Continue (confirms they saw the screen).
        user.onboarding = ob
        flag_modified(user, "onboarding")
        await db.commit()

    if not user.is_paid:
        await sendblue_service.send_message(
            raw_number,
            "need an active sub to coach you from here — open max and subscribe, then we can go back and forth.",
        )
        return

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
        return

    response_text = ""
    if body:
        text_for_model = body
        if first_thread_message:
            text_for_model = (
                "(internal: first message from them on this line — one warm short line, then answer. "
                "Do not mention that it's their first text, SMS, or iMessage. Stay under ~3 short sentences.)\n\n"
                + body
            )
        try:
            response_text, _choices = await process_chat_message(
                user_id=user_id_str,
                message_text=text_for_model,
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


async def _sendblue_process_inbound_payload(payload: dict) -> None:
    raw_number = str(payload.get("from_number") or payload.get("number") or "").strip()
    body = str(payload.get("content") or "").strip()
    media_url = str(payload.get("media_url") or "").strip()

    if not raw_number:
        return

    async with AsyncSessionLocal() as db:
        rds_cm = None
        rds_db = None
        try:
            rds_cm = RDSSessionLocal()
            rds_db = await rds_cm.__aenter__()
        except Exception as e:
            logger.info("Sendblue inbound without RDS session: %s", e)
            rds_cm = None
            rds_db = None
        try:
            await _sendblue_inbound_core(db, rds_db, raw_number, body, media_url)
        finally:
            if rds_cm is not None:
                try:
                    await rds_cm.__aexit__(None, None, None)
                except Exception:
                    pass


@router.post("/receive")
async def sendblue_receive_webhook(request: Request, background_tasks: BackgroundTasks):
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

    if payload.get("opted_out") is True:
        return {"ok": True, "ignored": "opted_out"}

    handle = payload.get("message_handle")
    if _seen_message(str(handle) if handle else ""):
        return {"ok": True, "duplicate": True}

    raw_number = str(payload.get("from_number") or payload.get("number") or "").strip()
    if not raw_number:
        return {"ok": True}

    background_tasks.add_task(_sendblue_process_inbound_payload, dict(payload))
    return {"ok": True, "queued": True}

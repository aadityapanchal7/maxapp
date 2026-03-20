"""
Ingest Twilio MMS images as user progress pictures (S3/local + DB).
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.sqlalchemy_models import User, UserProgressPhoto
from services.storage_service import storage_service

logger = logging.getLogger(__name__)

# Twilio delivers media URLs; cap download size for safety
MAX_MMS_IMAGE_BYTES = 15 * 1024 * 1024


async def download_twilio_media(url: str) -> tuple[Optional[bytes], str]:
    """Download bytes from Twilio MediaUrl; return (data, content_type)."""
    auth: Optional[tuple[str, str]] = None
    if settings.twilio_account_sid and settings.twilio_auth_token:
        auth = (settings.twilio_account_sid, settings.twilio_auth_token)

    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 401 and auth:
                resp = await client.get(url, auth=auth)
            if resp.status_code != 200:
                logger.warning("Twilio media GET failed status=%s url=%s", resp.status_code, url[:80])
                return None, "image/jpeg"
            ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            data = resp.content
            if len(data) > MAX_MMS_IMAGE_BYTES:
                logger.warning("Twilio media too large: %s bytes", len(data))
                return None, ct
            return data, ct
    except Exception as e:
        logger.error("Twilio media download error: %s", e, exc_info=True)
        return None, "image/jpeg"


async def ingest_mms_progress_photos_from_form(db: AsyncSession, user: User, form) -> int:
    """
    For each image in Twilio MMS, upload to storage and insert UserProgressPhoto (source=sms).
    Returns count successfully stored. Does not commit — caller commits.
    """
    try:
        num = int(form.get("NumMedia") or 0)
    except (TypeError, ValueError):
        num = 0
    if num <= 0:
        return 0

    uid = str(user.id)
    stored = 0
    for i in range(num):
        url = form.get(f"MediaUrl{i}")
        if not url:
            continue
        ct = str(form.get(f"MediaContentType{i}") or "image/jpeg")
        if not ct.lower().startswith("image/"):
            logger.info("Skipping non-image MMS part %s type=%s", i, ct)
            continue

        data, resolved_ct = await download_twilio_media(str(url))
        if not data:
            continue

        try:
            image_url = await storage_service.upload_progress_picture(data, uid, resolved_ct or ct)
        except Exception as e:
            logger.error("Progress picture upload failed for user %s: %s", uid, e, exc_info=True)
            continue
        if not image_url:
            logger.warning("Progress picture upload returned no URL for user %s", uid)
            continue

        photo = UserProgressPhoto(
            user_id=UUID(uid),
            image_url=image_url,
            created_at=datetime.utcnow(),
            source="sms",
        )
        db.add(photo)
        stored += 1
        logger.info("Stored MMS progress photo for user %s (%s)", uid, image_url[:60])

    return stored

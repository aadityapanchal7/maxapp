"""
Ingest MMS / chat images as user progress pictures (S3/local + DB).
Supports Twilio MMS URLs (basic auth) and Sendblue CDN URLs (public GET).
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import User, UserProgressPhoto
from services.storage_service import storage_service

logger = logging.getLogger(__name__)

MAX_MMS_IMAGE_BYTES = 15 * 1024 * 1024


async def download_mms_media_url(url: str) -> tuple[Optional[bytes], str]:
    """Download image bytes from a media URL (Sendblue CDN or public HTTPS)."""
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("MMS media GET failed status=%s url=%s", resp.status_code, url[:80])
                return None, "image/jpeg"
            ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            data = resp.content
            if len(data) > MAX_MMS_IMAGE_BYTES:
                logger.warning("MMS media too large: %s bytes", len(data))
                return None, ct
            return data, ct
    except Exception as e:
        logger.error("MMS media download error: %s", e, exc_info=True)
        return None, "image/jpeg"


async def ingest_sendblue_media_progress_photo(db: AsyncSession, user: User, media_url: str) -> int:
    """Store one Sendblue inbound image as UserProgressPhoto (source=sms). Caller commits."""
    if not media_url:
        return 0
    data, resolved_ct = await download_mms_media_url(media_url)
    if not data:
        return 0
    ct = resolved_ct or "image/jpeg"
    if not ct.lower().startswith("image/"):
        logger.info("Skipping non-image Sendblue media type=%s", ct)
        return 0
    uid = str(user.id)
    try:
        image_url = await storage_service.upload_progress_picture(data, uid, ct)
    except Exception as e:
        logger.error("Progress picture upload failed for user %s: %s", uid, e, exc_info=True)
        return 0
    if not image_url:
        return 0
    photo = UserProgressPhoto(
        user_id=UUID(uid),
        image_url=image_url,
        created_at=datetime.utcnow(),
        source="sms",
    )
    db.add(photo)
    logger.info("Stored Sendblue progress photo for user %s", uid)
    return 1


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

        data, resolved_ct = await download_mms_media_url(str(url))
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

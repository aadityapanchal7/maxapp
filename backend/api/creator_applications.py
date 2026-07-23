"""Creator application endpoints.

Creators who are well-known for something (or own a niche) apply to host their
own max on the marketplace. First-come-first-served: only one PENDING/APPROVED
application may claim a given max at a time — a second applicant for the same
niche is rejected with 409 so the urgency is real, not just copy.

`POST /creator-applications`      — submit an application.
`GET  /creator-applications/mine` — the caller's latest application (UI state).
`GET  /creator-applications/availability?max_name=…` — is a max still open?
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

from db.sqlalchemy import get_db
from middleware.auth_middleware import get_current_user
from middleware.rate_limit import rate_limit
from models.sqlalchemy_models import CreatorApplication, CreatorSocialConnection
from services import social_lookup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/creator-applications", tags=["CreatorApplications"])

# Statuses that "hold" a max so no one else can claim it.
_ACTIVE_STATUSES = ("pending", "approved")


def _normalize_max_name(name: str) -> str:
    """Lowercase, collapse whitespace, drop a trailing 'max' so 'Chess Max',
    'chessmax' and 'chess' all collide on the same niche."""
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    n = re.sub(r"\s*max$", "", n).strip()
    return n


def _normalize_handle(raw: str | None, platform: str) -> tuple[str | None, str | None]:
    """Turn whatever the user typed (a handle, an @handle, or a full URL) into a
    bare handle + canonical profile URL. Returns (handle, url) or (None, None).

    instagram → https://instagram.com/<handle>
    tiktok    → https://www.tiktok.com/@<handle>
    """
    if not raw:
        return None, None
    s = raw.strip()
    if not s:
        return None, None
    # If they pasted a URL, pull the last meaningful path segment.
    if "://" in s or s.lower().startswith("www.") or ".com/" in s.lower():
        try:
            parsed = urlparse(s if "://" in s else f"https://{s}")
            path = (parsed.path or "").strip("/")
            s = path.split("/")[0] if path else ""
        except Exception:
            s = ""
    s = s.lstrip("@").strip()
    # Valid handle chars only (letters, digits, dot, underscore).
    s = re.sub(r"[^A-Za-z0-9._]", "", s)
    if not s:
        return None, None
    if platform == "instagram":
        return s, f"https://instagram.com/{s}"
    if platform == "tiktok":
        return s, f"https://www.tiktok.com/@{s}"
    return s, None


class CreatorApplicationBody(BaseModel):
    applicant_name: str
    max_name: str
    max_description: str
    max_differentiator: str
    brand_fit: str
    instagram: str | None = None
    tiktok: str | None = None
    course_docs: list[dict] | None = None

    @field_validator("applicant_name", "max_name", "max_description", "max_differentiator", "brand_fit")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("required")
        return v.strip()


@router.post(
    "",
    dependencies=[Depends(rate_limit(limit=8, window_s=3600, scope="creator_apply"))],
)
async def submit_application(
    body: CreatorApplicationBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]

    # Prefer OAuth-verified handles (creator signed in to IG/TikTok).
    oauth_rows = (
        await db.execute(
            select(CreatorSocialConnection).where(
                (CreatorSocialConnection.user_id == user_id)
                & (CreatorSocialConnection.revoked_at.is_(None))
            )
        )
    ).scalars().all()
    oauth_by_platform = {r.platform: r for r in oauth_rows}

    # Basic length guards so a stray paste can't bloat the row.
    if len(body.applicant_name) > 120:
        raise HTTPException(status_code=422, detail="Name is too long.")
    if len(body.max_name) > 80:
        raise HTTPException(status_code=422, detail="Max name is too long.")
    if len(body.max_description) > 1500:
        raise HTTPException(status_code=422, detail="Description is too long (1500 char max).")
    if len(body.max_differentiator) > 1500:
        raise HTTPException(status_code=422, detail="Differentiator is too long (1500 char max).")
    if len(body.brand_fit) > 1500:
        raise HTTPException(status_code=422, detail="Brand fit is too long (1500 char max).")

    ig_handle, ig_url = _normalize_handle(body.instagram, "instagram")
    tt_handle, tt_url = _normalize_handle(body.tiktok, "tiktok")

    ig_oauth = oauth_by_platform.get("instagram")
    tt_oauth = oauth_by_platform.get("tiktok")
    if ig_oauth and ig_oauth.handle:
        ig_handle, ig_url = ig_oauth.handle, f"https://instagram.com/{ig_oauth.handle}"
    if tt_oauth and tt_oauth.handle:
        tt_handle, tt_url = tt_oauth.handle, f"https://www.tiktok.com/@{tt_oauth.handle}"

    if settings.creator_social_oauth_required:
        if not ig_oauth and not tt_oauth:
            raise HTTPException(
                status_code=422,
                detail="Link at least one Instagram or TikTok account via sign-in.",
            )
        if not ig_handle and not tt_handle:
            raise HTTPException(
                status_code=422,
                detail="Link at least one Instagram or TikTok account so we can verify you.",
            )

    normalized = _normalize_max_name(body.max_name)
    if not normalized:
        raise HTTPException(status_code=422, detail="Tell us which max you'd own.")

    # First-come-first-served — one creator per max. If someone already has a
    # pending/approved claim on this niche, this applicant is too late.
    taken = (
        await db.execute(
            select(CreatorApplication.id).where(
                (CreatorApplication.max_name_normalized == normalized)
                & (CreatorApplication.status.in_(_ACTIVE_STATUSES))
            ).limit(1)
        )
    ).first()
    if taken:
        raise HTTPException(
            status_code=409,
            detail="Someone's already in line for this max. It's first come, first served — try a different niche.",
        )

    # Pull public profile signal server-side (authoritative — the client can't
    # spoof follower counts). OAuth connections carry verified profile data;
    # social_lookup fills gaps for manual handles.
    social_stats: dict = {}
    if ig_handle:
        if ig_oauth and ig_oauth.profile:
            prof = dict(ig_oauth.profile)
            prof.update({"platform": "instagram", "handle": ig_handle, "found": True, "oauth_verified": True})
            social_stats["instagram"] = prof
        else:
            prof = await social_lookup.lookup_profile("instagram", ig_handle)
            if prof:
                social_stats["instagram"] = prof
    if tt_handle:
        if tt_oauth and tt_oauth.profile:
            prof = dict(tt_oauth.profile)
            prof.update({"platform": "tiktok", "handle": tt_handle, "found": True, "oauth_verified": True})
            social_stats["tiktok"] = prof
        else:
            prof = await social_lookup.lookup_profile("tiktok", tt_handle)
            if prof:
                social_stats["tiktok"] = prof

    app_row = CreatorApplication(
        user_id=user_id,
        applicant_name=body.applicant_name,
        max_name=body.max_name,
        max_name_normalized=normalized,
        max_description=body.max_description,
        max_differentiator=body.max_differentiator,
        brand_fit=body.brand_fit,
        course_docs=body.course_docs or [],
        instagram_handle=ig_handle,
        instagram_url=ig_url,
        tiktok_handle=tt_handle,
        tiktok_url=tt_url,
        social_stats=social_stats,
        status="pending",
    )
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)

    logger.info("[creator_apply] user=%s max=%s", user_id, normalized)
    return {
        "id": str(app_row.id),
        "status": app_row.status,
        "max_name": app_row.max_name,
        "instagram_url": app_row.instagram_url,
        "tiktok_url": app_row.tiktok_url,
        "social_stats": app_row.social_stats or {},
    }


class SocialLookupBody(BaseModel):
    platform: str  # 'instagram' | 'tiktok'
    handle: str


@router.post(
    "/social-lookup",
    dependencies=[Depends(rate_limit(limit=40, window_s=600, scope="creator_social_lookup"))],
)
async def social_lookup_endpoint(
    body: SocialLookupBody,
    current_user: dict = Depends(get_current_user),
):
    """Live preview for the apply flow — pulls public follower count + avatar so
    the creator can confirm they linked the right account before submitting."""
    platform = (body.platform or "").strip().lower()
    if platform not in ("instagram", "tiktok"):
        raise HTTPException(status_code=422, detail="Unknown platform.")
    profile = await social_lookup.lookup_profile(platform, body.handle)
    if not profile:
        raise HTTPException(status_code=422, detail="Enter a valid handle.")
    return profile


@router.get("/mine")
async def my_application(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(CreatorApplication)
            .where(CreatorApplication.user_id == current_user["id"])
            .order_by(CreatorApplication.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        return {"application": None}
    return {
        "application": {
            "id": str(row.id),
            "status": row.status,
            "applicant_name": row.applicant_name,
            "max_name": row.max_name,
            "max_description": row.max_description,
            "max_differentiator": row.max_differentiator,
            "brand_fit": row.brand_fit,
            "course_docs": row.course_docs or [],
            "instagram_url": row.instagram_url,
            "tiktok_url": row.tiktok_url,
            "social_stats": row.social_stats or {},
            # Surfaced so a rejected applicant sees WHY (was write-only before).
            "review_notes": row.review_notes or None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    }


@router.get("/availability")
async def availability(
    max_name: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Quick check the client can call before submit — is this max still open?"""
    normalized = _normalize_max_name(max_name)
    if not normalized:
        return {"available": False, "max_name": max_name}
    taken = (
        await db.execute(
            select(func.count(CreatorApplication.id)).where(
                (CreatorApplication.max_name_normalized == normalized)
                & (CreatorApplication.status.in_(_ACTIVE_STATUSES))
            )
        )
    ).scalar_one()
    return {"available": taken == 0, "max_name": max_name}


_MAX_DOC_BYTES = 25 * 1024 * 1024  # 25 MB per file


def _normalize_doc_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise HTTPException(status_code=422, detail="Enter a valid URL.")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


@router.post("/upload-doc")
async def upload_course_doc(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a course document (PDF, doc, slides, etc.) for the application."""
    # Bounded read: cap+1 so an oversized body 413s without full RAM buffer.
    data = await file.read(_MAX_DOC_BYTES + 1)
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail="File too large (25 MB max).")
    uid = str(current_user["id"])
    ext = os.path.splitext(file.filename or "doc")[1] or ".bin"
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", (file.filename or "document"))[:120]
    subdir = os.path.join(os.path.dirname(__file__), "..", "uploads", "creator_docs", uid)
    os.makedirs(subdir, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    stored = f"{stamp}_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(subdir, stored)
    with open(path, "wb") as f:
        f.write(data)
    url = f"/uploads/creator_docs/{uid}/{stored}"
    return {
        "filename": safe_name,
        "url": url,
        "content_type": file.content_type,
        "size_bytes": len(data),
        "source": "local",
    }


@router.post("/link-doc")
async def link_course_doc(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Attach a Google Drive (or other) share link as course material."""
    url = _normalize_doc_url(str(body.get("url") or ""))
    name = (body.get("filename") or "Google Drive link").strip()[:120]
    return {
        "filename": name,
        "url": url,
        "source": "gdrive" if "drive.google" in url or "docs.google" in url else "link",
    }

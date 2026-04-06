import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from middleware.auth_middleware import require_paid_user, get_current_user
from services.storage_service import storage_service
from services.llm_router import llm_analyze_triple_full
from models.sqlalchemy_models import Scan, Leaderboard, User
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scans", tags=["Face Scans"])


class RealtimeScanRequest(BaseModel):
    image: str
    include_visuals: bool = True
    timestamp: float | None = None


async def _update_leaderboard_after_scan(
    db: AsyncSession,
    user_uuid: UUID,
    overall_score: float | None,
) -> None:
    overall = float(overall_score or 0)
    leaderboard_score = overall * 10

    leaderboard_result = await db.execute(select(Leaderboard).where(Leaderboard.user_id == user_uuid))
    entry = leaderboard_result.scalar_one_or_none()

    if entry:
        entry.score = max(entry.score or 0, leaderboard_score)
        entry.level = overall
        entry.last_scan_at = datetime.utcnow()
        entry.scans_count = (entry.scans_count or 0) + 1
    else:
        entry = Leaderboard(
            user_id=user_uuid,
            score=leaderboard_score,
            level=overall,
            streak_days=1,
            improvement_percentage=0,
            scans_count=1,
            last_scan_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db.add(entry)

    await db.commit()

    all_entries_result = await db.execute(select(Leaderboard).order_by(Leaderboard.score.desc()))
    all_entries = all_entries_result.scalars().all()
    for rank, e in enumerate(all_entries, 1):
        e.rank = rank
    await db.commit()


async def _maybe_notify_scan_whatsapp(user: Optional[User], overall_score: Optional[float]) -> None:
    try:
        if not user:
            return
        from services.sendblue_service import sendblue_service, onboarding_allows_proactive_sms
        from services.notification_prefs import user_allows_proactive_push
        from services.apns_service import send_apns_alert
        import asyncio

        want_sms = bool(user.phone_number) and onboarding_allows_proactive_sms(user.onboarding)
        want_push = user_allows_proactive_push(user.onboarding, user.apns_device_token)
        if not want_sms and not want_push:
            return

        if want_sms:
            asyncio.create_task(
                sendblue_service.send_scan_complete(
                    user.phone_number,
                    user.email or "",
                    float(overall_score) if overall_score is not None else None,
                )
            )

        if want_push and (user.apns_device_token or "").strip():
            score_txt = (
                f"{float(overall_score):.1f}"
                if overall_score is not None
                else "ready"
            )
            title = "Max"
            body = (
                f"Your scan results are in (~{score_txt}/10). Open Max for the full breakdown."
            )
            tok = user.apns_device_token.strip()

            async def _do_push():
                await send_apns_alert(tok, title, body)

            asyncio.create_task(_do_push())
    except Exception as notif_err:
        logger.warning("Scan notification failed: %s", notif_err)


def _overall_from_analysis(analysis: dict) -> float:
    if not isinstance(analysis, dict):
        return 0.0
    pr = analysis.get("psl_rating")
    if isinstance(pr, dict) and pr.get("psl_score") is not None:
        try:
            return float(pr["psl_score"])
        except (TypeError, ValueError):
            pass
    o = analysis.get("scan_summary", {}).get("overall_score")
    if o is None:
        o = analysis.get("metrics", {}).get("overall_score") if isinstance(analysis.get("metrics"), dict) else None
    if o is None:
        o = analysis.get("overall_score", 0)
    try:
        return float(o)
    except (TypeError, ValueError):
        return 0.0


@router.post("/upload-triple")
async def upload_scan_triple(
    front: UploadFile = File(...),
    left: UploadFile = File(...),
    right: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Three still photos (front, left profile, right profile) → UMax-style 6 metrics + overall.
    Unpaid: one free scan. Basic: one face scan total (same as initial signup scan — no extras). Premium: one per UTC day.
    """
    user_uuid = UUID(current_user["id"])
    uid_str = str(user_uuid)

    user_row = await db.get(User, user_uuid)
    is_paid = bool(current_user.get("is_paid", False))
    tier = (current_user.get("subscription_tier") or "").lower()
    is_premium = is_paid and tier == "premium"

    if not is_paid:
        if user_row and user_row.first_scan_completed:
            raise HTTPException(status_code=400, detail="You have already completed your free face scan. Subscribe to scan again.")
    elif not is_premium:
        # Basic: one scan only (typically the signup / onboarding scan — no additional scans on Basic).
        if user_row and user_row.first_scan_completed:
            raise HTTPException(
                status_code=400,
                detail="Basic includes one face scan. Upgrade to Premium for daily scans.",
            )
    else:
        # Premium tier: one scan per day (UTC)
        now = datetime.utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        today_res = await db.execute(
            select(Scan.id)
            .where(Scan.user_id == user_uuid)
            .where(Scan.created_at >= day_start)
            .where(Scan.created_at < day_end)
            .limit(1)
        )
        if today_res.first():
            raise HTTPException(status_code=429, detail="You already completed a face scan today. Try again tomorrow.")

    onboarding_ctx = json.dumps(user_row.onboarding or {}, default=str) if user_row else "{}"

    front_data = await front.read()
    left_data = await left.read()
    right_data = await right.read()
    if not front_data or not left_data or not right_data:
        raise HTTPException(status_code=400, detail="All three images (front, left, right) are required")

    front_url = await storage_service.upload_image(front_data, uid_str, "front")
    left_url = await storage_service.upload_image(left_data, uid_str, "left")
    right_url = await storage_service.upload_image(right_data, uid_str, "right")
    if not all([front_url, left_url, right_url]):
        raise HTTPException(status_code=500, detail="Failed to store images")

    scan_row = Scan(
        user_id=user_uuid,
        created_at=datetime.utcnow(),
        is_unlocked=is_paid,
        processing_status="processing",
        scan_type="triple_gemini",
        images={"front": front_url, "left": left_url, "right": right_url},
    )
    db.add(scan_row)
    await db.commit()
    await db.refresh(scan_row)
    scan_id = str(scan_row.id)

    try:
        analysis = await llm_analyze_triple_full(front_data, left_data, right_data, onboarding_ctx)
        scan_row.analysis = analysis
        scan_row.processing_status = "completed"
        await db.commit()

        user = await db.get(User, user_uuid)
        if user and not user.first_scan_completed:
            user.first_scan_completed = True
            ob = dict(user.onboarding or {})
            pi = analysis.get("profile_insights") or {}
            pr = analysis.get("psl_rating") if isinstance(analysis.get("psl_rating"), dict) else {}
            ob["facial_scan_summary"] = {
                "overall_score": analysis.get("overall_score"),
                "psl_score": pr.get("psl_score"),
                "psl_tier": pr.get("psl_tier"),
                "appeal": pr.get("appeal"),
                "potential_score": analysis.get("potential_score"),
                "archetype": pi.get("archetype"),
                "suggested_modules": pi.get("suggested_modules") or [],
                "scan_completed_at": datetime.utcnow().isoformat() + "Z",
            }
            user.onboarding = ob
            await db.commit()

        overall_score = _overall_from_analysis(analysis)
        await _update_leaderboard_after_scan(db, user_uuid, overall_score)
        await _maybe_notify_scan_whatsapp(user, overall_score)

        return {"scan_id": scan_id, "analysis": analysis}
    except Exception as e:
        scan_row.processing_status = "failed"
        scan_row.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.post("/upload-video")
async def upload_scan_video(
    video: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deprecated: app uses three-photo Gemini scan (`/scans/upload-triple`)."""
    await video.read()  # consume body
    raise HTTPException(
        status_code=400,
        detail="Video scans are no longer supported. Use the three-photo face scan in the app.",
    )


@router.post("/realtime")
async def analyze_realtime_scan(
    payload: RealtimeScanRequest,
    current_user: dict = Depends(get_current_user),
):
    """Realtime overlay was backed by Cannon; disabled with Gemini-only scan flow."""
    raise HTTPException(status_code=501, detail="Realtime facial preview is not available.")


@router.post("/{scan_id}/analyze")
async def analyze_scan(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run Gemini analysis for an image triple stored on the scan (not used for triple_gemini uploads)."""
    try:
        scan_uuid = UUID(scan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scan ID format")

    user_uuid = UUID(current_user["id"])
    result = await db.execute(
        select(Scan).where((Scan.id == scan_uuid) & (Scan.user_id == user_uuid))
    )
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.scan_type == "triple_gemini":
        if scan.processing_status == "completed":
            return {"message": "Analysis already completed", "scan_id": scan_id}
        raise HTTPException(status_code=400, detail="Triple scans are analyzed during upload")

    if scan.scan_type == "video":
        raise HTTPException(status_code=400, detail="Video scans are no longer supported")

    scan.processing_status = "processing"
    await db.commit()

    try:
        front_url = (scan.images or {}).get("front")
        left_url = (scan.images or {}).get("left")
        right_url = (scan.images or {}).get("right")

        if not all([front_url, left_url, right_url]):
            raise HTTPException(status_code=400, detail="Missing image URLs")

        if front_url.startswith("/uploads/"):
            front_data = await storage_service.get_image(front_url)
            left_data = await storage_service.get_image(left_url)
            right_data = await storage_service.get_image(right_url)
        else:
            import httpx

            async with httpx.AsyncClient() as client:
                front_resp = await client.get(front_url)
                left_resp = await client.get(left_url)
                right_resp = await client.get(right_url)
            front_data = front_resp.content
            left_data = left_resp.content
            right_data = right_resp.content

        if not all([front_data, left_data, right_data]):
            raise HTTPException(status_code=500, detail="Failed to retrieve images")

        user_orm = await db.get(User, user_uuid)
        onboarding_ctx = json.dumps(user_orm.onboarding or {}, default=str) if user_orm else "{}"
        analysis = await llm_analyze_triple_full(front_data, left_data, right_data, onboarding_ctx)
        scan.analysis = analysis
        scan.processing_status = "completed"
        await db.commit()

        overall_score = _overall_from_analysis(analysis)

        scans_result = await db.execute(
            select(Scan)
            .where((Scan.user_id == user_uuid) & (Scan.processing_status == "completed"))
            .order_by(Scan.created_at.desc())
        )
        user_scans = scans_result.scalars().all()
        scores = []
        for s in user_scans:
            scores.append(_overall_from_analysis(s.analysis or {}))

        improvement_percentage = 0
        if len(scores) >= 2:
            first_score = scores[-1] or 0
            latest_score = scores[0] or 0
            if first_score > 0:
                improvement_percentage = ((latest_score - first_score) / first_score) * 100

        leaderboard_result = await db.execute(select(Leaderboard).where(Leaderboard.user_id == user_uuid))
        entry = leaderboard_result.scalar_one_or_none()

        if entry:
            entry.score = max(entry.score or 0, (overall_score or 0) * 10)
            entry.level = overall_score or 0
            entry.improvement_percentage = improvement_percentage
            entry.last_scan_at = datetime.utcnow()
            entry.scans_count = (entry.scans_count or 0) + 1
        else:
            entry = Leaderboard(
                user_id=user_uuid,
                score=(overall_score or 0) * 10,
                level=overall_score or 0,
                streak_days=1,
                improvement_percentage=improvement_percentage,
                scans_count=1,
                last_scan_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
            )
            db.add(entry)

        await db.commit()

        all_entries_result = await db.execute(select(Leaderboard).order_by(Leaderboard.score.desc()))
        all_entries = all_entries_result.scalars().all()
        for rank, e in enumerate(all_entries, 1):
            e.rank = rank
        await db.commit()

        return {"message": "Analysis complete", "scan_id": scan_id}

    except HTTPException:
        raise
    except Exception as e:
        scan.processing_status = "failed"
        scan.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.get("/latest")
async def get_latest_scan(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get most recent scan"""
    user_uuid = UUID(current_user["id"])
    result = await db.execute(
        select(Scan).where(Scan.user_id == user_uuid).order_by(Scan.created_at.desc()).limit(1)
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="No scans found")

    is_paid = current_user.get("is_paid", False)
    response = {
        "id": str(scan.id),
        "created_at": scan.created_at,
        "images": scan.images or {},
        "is_unlocked": is_paid,
        "processing_status": scan.processing_status,
    }

    if scan.analysis:
        if is_paid:
            response["analysis"] = scan.analysis
        else:
            a = scan.analysis or {}
            overall_score = _overall_from_analysis(a)
            try:
                pot = float(a.get("potential_score", overall_score))
            except (TypeError, ValueError):
                pot = overall_score
            pot = max(0.0, min(10.0, pot))
            pr = a.get("psl_rating") if isinstance(a.get("psl_rating"), dict) else {}
            appeal = overall_score
            try:
                if pr.get("appeal") is not None:
                    appeal = float(pr["appeal"])
            except (TypeError, ValueError):
                pass
            appeal = max(0.0, min(10.0, appeal))
            tier_s = pr.get("psl_tier") if isinstance(pr.get("psl_tier"), str) else ""
            arch_s = pr.get("archetype") if isinstance(pr.get("archetype"), str) else ""
            try:
                asc_m = int(pr.get("ascension_time_months") or 0)
            except (TypeError, ValueError):
                asc_m = 0
            try:
                age_s = int(pr.get("age_score") or 0)
            except (TypeError, ValueError):
                age_s = 0
            response["analysis"] = {
                "overall_score": overall_score,
                "potential_score": pot,
                "scan_summary": a.get("scan_summary") or {"overall_score": overall_score},
                "umax_metrics": a.get("umax_metrics"),
                "preview_blurb": a.get("preview_blurb"),
                "psl_rating": {
                    "psl_score": overall_score,
                    "potential": pot,
                    "appeal": appeal,
                    "psl_tier": tier_s,
                    "ascension_time_months": max(0, min(120, asc_m)),
                    "age_score": max(0, min(99, age_s)),
                    "archetype": arch_s[:200] if arch_s else "",
                },
                "locked": True,
            }

    return response


@router.get("/history")
async def get_scan_history(
    limit: int = 10,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Get scan history (paid only)"""
    user_uuid = UUID(current_user["id"])
    result = await db.execute(
        select(Scan)
        .where(Scan.user_id == user_uuid)
        .order_by(Scan.created_at.desc())
        .limit(limit)
    )
    scans_list = result.scalars().all()
    scans = []
    for s in scans_list:
        scans.append(
            {
                "id": str(s.id),
                "created_at": s.created_at,
                "overall_score": _overall_from_analysis(s.analysis or {}),
            }
        )
    return {"scans": scans}


@router.get("/{scan_id}")
async def get_scan_by_id(
    scan_id: str,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific scan with full analysis (paid only)"""
    try:
        scan_uuid = UUID(scan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scan ID format")

    user_uuid = UUID(current_user["id"])
    result = await db.execute(
        select(Scan).where((Scan.id == scan_uuid) & (Scan.user_id == user_uuid))
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    return {
        "id": str(scan.id),
        "created_at": scan.created_at,
        "images": scan.images or {},
        "analysis": scan.analysis,
        "processing_status": scan.processing_status,
        # Paid route — helps clients treat the row as unlocked if JWT `is_paid` lags after subscribe.
        "is_unlocked": True,
    }

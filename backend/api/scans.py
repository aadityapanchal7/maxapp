import asyncio
import json
import logging
from typing import Optional

# Hard ceiling on a single face-scan vision analysis. Prevents a hung LLM
# provider from leaving the client stuck on "Analyzing…" forever — on timeout
# the scan is marked failed and the app shows a retry instead of hanging.
_SCAN_ANALYSIS_TIMEOUT_S = 75.0

# A scan can only legitimately sit in "processing" for as long as the analysis
# timeout allows. If the server dies mid-analysis (deploy/restart/OOM) the
# except-blocks never run and the row is stranded in "processing" — which the
# app renders as an eternal Analyzing screen. Any read older than this gets
# reaped to "failed" so clients fall into their retry UI instead of hanging.
_STALE_PROCESSING_S = _SCAN_ANALYSIS_TIMEOUT_S + 105.0  # 3 min total

# Per-image upload cap. A face photo is well under this; the limit stops a
# malicious/buggy client from forcing the server to buffer + vision-analyze a
# huge payload (memory exhaustion + runaway LLM cost).
_MAX_IMAGE_BYTES = 12 * 1024 * 1024  # 12 MB


def _validate_image_upload(data: bytes, content_type: Optional[str], label: str) -> None:
    """Reject oversized or non-image uploads before any expensive processing."""
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"{label} image is too large (max {_MAX_IMAGE_BYTES // (1024 * 1024)}MB).",
        )
    ct = (content_type or "").lower()
    if ct and not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"{label} must be an image.")

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from db import get_db
from middleware.auth_middleware import require_paid_user, get_current_user
from middleware.rate_limit import rate_limit
from services.storage_service import storage_service
from services.llm_router import llm_analyze_triple_full
from models.sqlalchemy_models import Scan, Leaderboard, User
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scans", tags=["Face Scans"])

# Strong references to fire-and-forget notification tasks. asyncio only keeps a
# WEAK reference to a bare create_task result, so without this the scan-complete
# push/SMS could be garbage-collected mid-flight and never actually send.
_bg_tasks: set = set()


def _spawn_bg(coro):
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)
    return t


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

    def _apply(e: Leaderboard) -> None:
        e.score = max(e.score or 0, leaderboard_score)
        e.level = overall
        e.last_scan_at = datetime.utcnow()
        e.scans_count = (e.scans_count or 0) + 1

    if entry:
        _apply(entry)
        await db.commit()
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
        try:
            await db.commit()
        except IntegrityError:
            # Concurrent first scan already created the row — fold this scan into
            # the winner instead of 500ing on the unique user_id violation.
            await db.rollback()
            entry = (await db.execute(
                select(Leaderboard).where(Leaderboard.user_id == user_uuid)
            )).scalar_one_or_none()
            if entry is not None:
                _apply(entry)
                await db.commit()
    # NOTE: rank is computed on read (see api/leaderboard.py). We no longer
    # rewrite every row's rank on each scan — that was O(n) writes per upload
    # and serialized concurrent scans.


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
            _spawn_bg(
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

            _spawn_bg(_do_push())
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


def _redacted_analysis(analysis: dict) -> dict:
    """Paywall-safe projection of a scan analysis for NON-paid users.

    Returns only the teaser fields the locked results UI needs (overall, a
    capped potential, appeal, tier/archetype/ascension) and drops the full
    per-feature breakdown (feature_scores, proportions, side_profile, etc.).
    `locked: True` tells the client to render lock icons. Used everywhere a
    free user can receive an analysis — both the live upload response and the
    latest-scan fetch — so the complete paid analysis never crosses the wire."""
    a = analysis or {}
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
    try:
        asc_m = int(pr.get("ascension_time_months") or 0)
    except (TypeError, ValueError):
        asc_m = 0
    try:
        age_s = int(pr.get("age_score") or 0)
    except (TypeError, ValueError):
        age_s = 0
    return {
        "overall_score": overall_score,
        "potential_score": pot,
        "scan_summary": a.get("scan_summary") or {"overall_score": overall_score},
        # umax_metrics and preview_blurb are premium — omitted for free users (P0-3).
        "psl_rating": {
            "psl_score": overall_score,
            "potential": pot,
            "appeal": appeal,
            "psl_tier": tier_s,
            "ascension_time_months": max(0, min(120, asc_m)),
            "age_score": max(0, min(99, age_s)),
            # Archetype is a locked metric card: its label is static client-side
            # and its value is masked ("—") until paid, so the redacted payload
            # must NOT carry the real archetype (it would be a value leak on the
            # wire even though the UI masks it). The full analysis sent to paid
            # users still includes it. (Ralph Task E.)
            "archetype": "",
        },
        "locked": True,
    }


@router.post(
    "/upload-triple",
    dependencies=[Depends(rate_limit(limit=20, window_s=3600, scope="scan"))],
)
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
    is_scan_user = bool(current_user.get("is_scan_user", False))
    is_paid = bool(current_user.get("is_paid", False))
    tier = (current_user.get("subscription_tier") or "").lower()
    is_premium = is_paid and tier == "premium"

    # Tier-based scan rate limiting
    #   Scan-user (admin/internal): unlimited
    #   Free (not paid):  1 lifetime
    #   Chadlite (basic): 1 per ROLLING 7-DAY WINDOW (weekly)
    #   Chad (premium):   1 per UTC DAY (daily)
    if is_scan_user:
        pass
    elif not is_paid:
        if user_row and user_row.first_scan_completed:
            raise HTTPException(
                status_code=400,
                detail="You have already completed your free face scan. Subscribe to scan again.",
            )
    elif not is_premium:
        # Chadlite — once per rolling 7-day window
        now = datetime.utcnow()
        week_start = now - timedelta(days=7)
        recent_res = await db.execute(
            select(Scan.id, Scan.created_at)
            .where(Scan.user_id == user_uuid)
            .where(Scan.created_at >= week_start)
            .where(Scan.processing_status != "failed")
            .order_by(Scan.created_at.desc())
            .limit(1)
        )
        recent_row = recent_res.first()
        if recent_row:
            last_scan_at = recent_row[1]
            next_at = last_scan_at + timedelta(days=7)
            wait_days = max(1, (next_at - now).days + 1)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Chadlite includes 1 face scan per week. "
                    f"Try again in ~{wait_days} day{'s' if wait_days != 1 else ''}, "
                    f"or upgrade to Chad for daily scans."
                ),
            )
    else:
        # Chad — once per UTC day
        now = datetime.utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        today_res = await db.execute(
            select(Scan.id)
            .where(Scan.user_id == user_uuid)
            .where(Scan.created_at >= day_start)
            .where(Scan.created_at < day_end)
            .where(Scan.processing_status != "failed")
            .limit(1)
        )
        if today_res.first():
            raise HTTPException(
                status_code=429,
                detail="You already completed a face scan today. Try again tomorrow.",
            )

    onboarding_ctx = json.dumps(user_row.onboarding or {}, default=str) if user_row else "{}"

    # Bounded reads: read at most cap+1 bytes so an oversized upload trips the
    # 413 below WITHOUT first being buffered whole into RAM (OOM vector — and a
    # process death here strands every in-flight scan in "processing").
    front_data = await front.read(_MAX_IMAGE_BYTES + 1)
    left_data = await left.read(_MAX_IMAGE_BYTES + 1)
    right_data = await right.read(_MAX_IMAGE_BYTES + 1)
    if not front_data or not left_data or not right_data:
        raise HTTPException(status_code=400, detail="All three images (front, left, right) are required")
    _validate_image_upload(front_data, front.content_type, "Front")
    _validate_image_upload(left_data, left.content_type, "Left")
    _validate_image_upload(right_data, right.content_type, "Right")

    # Upload the three images concurrently — they're independent, so there's no
    # reason to pay three sequential round-trips to storage.
    front_url, left_url, right_url = await asyncio.gather(
        storage_service.upload_image(front_data, uid_str, "front"),
        storage_service.upload_image(left_data, uid_str, "left"),
        storage_service.upload_image(right_data, uid_str, "right"),
    )
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
        analysis = await asyncio.wait_for(
            llm_analyze_triple_full(front_data, left_data, right_data, onboarding_ctx),
            timeout=_SCAN_ANALYSIS_TIMEOUT_S,
        )

        # First-scan cap: if this is the user's first scan, force psl_tier
        # to be no higher than HTN. The LLM occasionally hands back
        # Chadlite/Chad on a first scan, which inflates expectations and
        # cuts off the upgrade ladder. Subsequent scans uncap.
        user = await db.get(User, user_uuid)
        is_first_scan = bool(user and not user.first_scan_completed)
        if is_first_scan:
            from services.gemini_service import _infer_psl_tier_from_score
            pr = analysis.get("psl_rating")
            if isinstance(pr, dict):
                try:
                    score_val = float(pr.get("psl_score") or analysis.get("overall_score") or 0.0)
                except (TypeError, ValueError):
                    score_val = 0.0
                pr["psl_tier"] = _infer_psl_tier_from_score(
                    score_val, is_first_scan=True,
                )

        scan_row.analysis = analysis
        scan_row.processing_status = "completed"
        await db.commit()

        if user and not user.first_scan_completed:
            user.first_scan_completed = True
            # Auto-set the profile picture to the front photo from this first
            # scan (the onboarding scan, or whenever the first scan happens) —
            # but never clobber an avatar they've already chosen themselves.
            prof = dict(user.profile or {})
            if not prof.get("avatar_url") and front_url:
                prof["avatar_url"] = front_url
                user.profile = prof
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
                # New viral metrics.
                "halo_feature": pr.get("halo_feature") or pi.get("halo_feature"),
                "bottleneck": pr.get("bottleneck") or pi.get("bottleneck"),
                "bottleneck_max": pr.get("bottleneck_max") or pi.get("bottleneck_max"),
                "sex_appeal": pr.get("sex_appeal"),
                "trust_appeal": pr.get("trust_appeal"),
                "appeal_quadrant": pr.get("appeal_quadrant"),
                "dimorphism": pr.get("dimorphism"),
                "dimorphism_note": pr.get("dimorphism_note"),
                "glow_up_label": pr.get("glow_up_label"),
                "first_move": pr.get("first_move") or pi.get("first_move") or [],
                "scan_completed_at": datetime.utcnow().isoformat() + "Z",
            }
            user.onboarding = ob
            await db.commit()

        overall_score = _overall_from_analysis(analysis)
        await _update_leaderboard_after_scan(db, user_uuid, overall_score)
        await _maybe_notify_scan_whatsapp(user, overall_score)

        # Never ship the full analysis to a non-paid user — even though the
        # client currently only reads overall_score, the raw response is
        # network-inspectable. Free users get the same redacted teaser the
        # locked results screen renders; paid users get the full analysis.
        treat_as_paid = is_paid or is_scan_user
        out_analysis = analysis if treat_as_paid else _redacted_analysis(analysis)
        return {"scan_id": scan_id, "analysis": out_analysis}
    except asyncio.TimeoutError:
        scan_row.processing_status = "failed"
        scan_row.error_message = "analysis_timeout"
        await db.commit()
        raise HTTPException(
            status_code=504,
            detail="Your scan took too long to analyze. Please try again.",
        )
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
    # NOTE: do NOT `await video.read()` here — multipart parsing has already
    # consumed the request body (spooled to disk); reading it back would load
    # an arbitrarily large video into RAM just to discard it (OOM vector).
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
            # Fetch the three angles concurrently (were 3 sequential round-trips).
            front_data, left_data, right_data = await asyncio.gather(
                storage_service.get_image(front_url),
                storage_service.get_image(left_url),
                storage_service.get_image(right_url),
            )
        else:
            import httpx

            async with httpx.AsyncClient() as client:
                front_resp, left_resp, right_resp = await asyncio.gather(
                    client.get(front_url),
                    client.get(left_url),
                    client.get(right_url),
                )
            front_data = front_resp.content
            left_data = left_resp.content
            right_data = right_resp.content

        if not all([front_data, left_data, right_data]):
            raise HTTPException(status_code=500, detail="Failed to retrieve images")

        user_orm = await db.get(User, user_uuid)
        onboarding_ctx = json.dumps(user_orm.onboarding or {}, default=str) if user_orm else "{}"
        analysis = await asyncio.wait_for(
            llm_analyze_triple_full(front_data, left_data, right_data, onboarding_ctx),
            timeout=_SCAN_ANALYSIS_TIMEOUT_S,
        )
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
            await db.commit()
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
            try:
                await db.commit()
            except IntegrityError:
                # Two near-simultaneous scans (retry/double-upload) both insert
                # the first leaderboard row; the loser violates the unique
                # user_id. Roll back, re-select the winner and fold this scan in.
                await db.rollback()
                entry = (await db.execute(
                    select(Leaderboard).where(Leaderboard.user_id == user_uuid)
                )).scalar_one_or_none()
                if entry is not None:
                    entry.score = max(entry.score or 0, (overall_score or 0) * 10)
                    entry.level = overall_score or 0
                    entry.improvement_percentage = improvement_percentage
                    entry.last_scan_at = datetime.utcnow()
                    entry.scans_count = (entry.scans_count or 0) + 1
                    await db.commit()
        # rank is computed on read (api/leaderboard.py); no O(n) rewrite here.

        return {"message": "Analysis complete", "scan_id": scan_id}

    except HTTPException:
        raise
    except Exception as e:
        # Roll back first: if the failure was an IntegrityError (e.g. the
        # leaderboard upsert racing another scan), the session is poisoned and
        # this commit would itself raise PendingRollbackError — losing the
        # 'failed' status marker. scan was committed as 'processing' earlier, so
        # it's still persistent after the rollback.
        await db.rollback()
        scan.processing_status = "failed"
        scan.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


async def _reap_if_stale_processing(scan: "Scan", db: AsyncSession) -> None:
    """Flip a scan stranded in "processing" to "failed" on read.

    In-process failures already mark rows failed, but a process death mid-
    analysis (deploy, restart, OOM) strands the row — and the app's results
    gate polls it forever. Reaping on the read path unwedges every stuck
    client on its next poll, with no app update required.
    """
    if scan.processing_status != "processing":
        return
    created = scan.created_at
    if created is None:
        return
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_s = (datetime.now(timezone.utc) - created).total_seconds()
    if age_s < _STALE_PROCESSING_S:
        return
    scan.processing_status = "failed"
    scan.error_message = "stale_processing_reaped"
    try:
        await db.commit()
    except Exception:
        await db.rollback()


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
        # 200 + null body. 404 here was historical and confused the mobile app:
        # any client that didn't catch the AxiosError stayed wedged on the
        # home loading state when a fresh user (faux-skip-signup) had no scans.
        # "No latest scan" is a normal data state, not a missing route.
        return None

    await _reap_if_stale_processing(scan, db)

    is_paid = current_user.get("is_paid", False)
    is_scan_user = current_user.get("is_scan_user", False)
    treat_as_paid = is_paid or is_scan_user
    # First scan ever? The full analysis breakdown is only shown for the user's
    # very first scan; daily/repeat scans show just the three headline metrics.
    # The latest scan is the first iff it's the only completed one.
    completed_count = int((await db.execute(
        select(func.count(Scan.id)).where(
            Scan.user_id == user_uuid,
            Scan.processing_status == "completed",
        )
    )).scalar() or 0)

    response = {
        "id": str(scan.id),
        "created_at": scan.created_at,
        "images": scan.images or {},
        "is_unlocked": treat_as_paid,
        "processing_status": scan.processing_status,
        "is_first_scan": completed_count <= 1,
    }

    if scan.analysis:
        response["analysis"] = scan.analysis if treat_as_paid else _redacted_analysis(scan.analysis)

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
        a = s.analysis or {}
        pr = a.get("psl_rating") if isinstance(a.get("psl_rating"), dict) else {}
        appeal_raw = pr.get("appeal")
        potential_raw = pr.get("potential") if pr.get("potential") not in (None, "") else a.get("potential_score")
        imgs = s.images if isinstance(s.images, dict) else {}
        scans.append(
            {
                "id": str(s.id),
                "created_at": s.created_at,
                "overall_score": _overall_from_analysis(a),
                "appeal": float(appeal_raw) if appeal_raw not in (None, "") else None,
                "potential": float(potential_raw) if potential_raw not in (None, "") else None,
                # Front photo for a thumbnail preview in the archive list.
                "front_image": imgs.get("front"),
                "images": {"front": imgs.get("front")},
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

    await _reap_if_stale_processing(scan, db)

    return {
        "id": str(scan.id),
        "created_at": scan.created_at,
        "images": scan.images or {},
        "analysis": scan.analysis,
        "processing_status": scan.processing_status,
        # Paid route — helps clients treat the row as unlocked if JWT `is_paid` lags after subscribe.
        "is_unlocked": True,
    }

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from db import get_db
from middleware.auth_middleware import require_paid_user, get_current_user
from services.storage_service import storage_service
from services.facial_analysis_client import facial_analysis_client
from models.sqlalchemy_models import Scan, Leaderboard, User
from pydantic import BaseModel

router = APIRouter(prefix="/scans", tags=["Face Scans"])


class RealtimeScanRequest(BaseModel):
    image: str
    include_visuals: bool = True
    timestamp: float | None = None


@router.post("/upload-video")
async def upload_scan_video(
    video: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a 15-second face scan video and analyze directly"""
    user_id = current_user["id"]
    user_uuid = UUID(user_id)

    # Read video data directly without saving locally
    video_data = await video.read()

    if not video_data:
        raise HTTPException(status_code=400, detail="No video data received")

    # Create scan record without video URL since we're not storing it
    scan_doc = Scan(
        user_id=user_uuid,
        processing_status="processing",
        is_unlocked=current_user.get("is_paid", False)
    )

    db.add(scan_doc)
    await db.commit()
    await db.refresh(scan_doc)
    scan_id = str(scan_doc.id)

    # Send video directly to cannon_facial_analysis service
    try:
        analysis = await facial_analysis_client.upload_video(video_data)

        # Update scan with analysis results
        scan_doc.analysis = analysis
        scan_doc.processing_status = "completed"
        await db.commit()

        # Update user first scan status
        user = await db.get(User, user_uuid)
        if user and not user.first_scan_completed:
            user.first_scan_completed = True
            await db.commit()

        # Update leaderboard (reuse existing logic)
        overall_score = 0.0
        if isinstance(analysis, dict):
            overall_score = analysis.get("scan_summary", {}).get("overall_score")
            if overall_score is None:
                overall_score = analysis.get("metrics", {}).get("overall_score")
            if overall_score is None:
                overall_score = analysis.get("overall_score", 0.0)

        # Calculate leaderboard score and update
        leaderboard_score = (float(overall_score) if overall_score else 0) * 10

        leaderboard_result = await db.execute(
            select(Leaderboard).where(Leaderboard.user_id == user_uuid)
        )
        existing_entry = leaderboard_result.scalar_one_or_none()

        if existing_entry:
            new_score = max(existing_entry.score or 0, leaderboard_score)
            existing_entry.score = new_score
            existing_entry.level = float(overall_score) if overall_score else 0
            existing_entry.last_scan_at = datetime.utcnow()
            existing_entry.scans_count = (existing_entry.scans_count or 0) + 1
        else:
            new_entry = Leaderboard(
                user_id=user_uuid,
                score=leaderboard_score,
                level=float(overall_score) if overall_score else 0,
                streak_days=1,
                improvement_percentage=0,
                scans_count=1,
                last_scan_at=datetime.utcnow()
            )
            db.add(new_entry)

        await db.commit()

        # Recalculate ranks
        all_entries_result = await db.execute(
            select(Leaderboard).order_by(Leaderboard.score.desc())
        )
        all_entries = all_entries_result.scalars().all()
        for rank, entry in enumerate(all_entries, 1):
            entry.rank = rank
        await db.commit()

        # Send WhatsApp notification if user has phone number (non-blocking)
        try:
            user_doc = await db.get(User, user_uuid)
            if user_doc and user_doc.phone_number:
                from services.twilio_service import twilio_service
                import asyncio
                asyncio.create_task(twilio_service.send_scan_complete(
                    user_doc.phone_number,
                    user_doc.email or "",
                    float(overall_score) if overall_score else None
                ))
        except Exception as notif_err:
            import logging
            logging.getLogger(__name__).warning(f"Scan notification failed: {notif_err}")

        return {"scan_id": scan_id, "analysis": analysis}

    except Exception as e:
        scan_doc.processing_status = "failed"
        scan_doc.analysis = {"error_message": str(e)}
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.post("/realtime")
async def analyze_realtime_scan(
    payload: RealtimeScanRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Lightweight proxy to the cannon_facial_analysis /scan/analyze-realtime endpoint.

    Used by the mobile/web face scan UI to fetch a live MediaPipe mesh overlay and
    basic head-pose / quality feedback while recording.
    """
    try:
        result = await facial_analysis_client.analyze_realtime(
            image_data_url=payload.image,
            include_visuals=payload.include_visuals,
            timestamp=payload.timestamp,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Realtime analysis failed: {e}")


@router.post("/{scan_id}/analyze")
async def analyze_scan(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Trigger AI analysis for uploaded scan (supports only image scans now)"""
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

    # Check if already processing
    if scan.processing_status == "processing":
        raise HTTPException(status_code=400, detail="Scan is already being analyzed")

    if scan.processing_status == "completed":
        return {"message": "Analysis already completed", "scan_id": scan_id}

    scan.processing_status = "processing"
    await db.commit()

    try:
        # Handle legacy image scan only
        front_url = scan.images.get("front") if scan.images else None
        left_url = scan.images.get("left") if scan.images else None
        right_url = scan.images.get("right") if scan.images else None

        if not all([front_url, left_url, right_url]):
            raise HTTPException(status_code=400, detail="Missing image URLs")

        front_data = None
        left_data = None
        right_data = None

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

        analysis = await facial_analysis_client.analyze_frames([front_data, left_data, right_data])

        scan.analysis = analysis
        scan.processing_status = "completed"
        await db.commit()

        # Update leaderboard entry for this user
        overall_score = 0.0
        if isinstance(analysis, dict):
            overall_score = analysis.get("scan_summary", {}).get("overall_score")
            if overall_score is None:
                overall_score = analysis.get("metrics", {}).get("overall_score")
            if overall_score is None:
                overall_score = analysis.get("overall_score", 0.0)

        # Get all completed scans for this user to calculate improvement
        all_scans_result = await db.execute(
            select(Scan)
            .where((Scan.user_id == user_uuid) & (Scan.processing_status == "completed"))
            .order_by(Scan.created_at.desc())
        )
        user_scans = []
        for s in all_scans_result.scalars().all():
            a = s.analysis or {}
            score = a.get("scan_summary", {}).get("overall_score")
            if score is None:
                score = a.get("metrics", {}).get("overall_score")
            if score is None:
                score = a.get("overall_score", 0)
            user_scans.append({"score": score, "created_at": s.created_at})

        # Calculate improvement percentage (compare first to latest)
        improvement_percentage = 0
        if len(user_scans) >= 2:
            first_score = user_scans[-1]["score"] or 0
            latest_score = user_scans[0]["score"] or 0
            if first_score > 0:
                improvement_percentage = ((latest_score - first_score) / first_score) * 100

        # Calculate score for leaderboard
        leaderboard_score = (float(overall_score) if overall_score else 0) * 10

        # Update or create leaderboard entry
        leaderboard_result = await db.execute(
            select(Leaderboard).where(Leaderboard.user_id == user_uuid)
        )
        existing_entry = leaderboard_result.scalar_one_or_none()

        if existing_entry:
            new_score = max(existing_entry.score or 0, leaderboard_score)
            existing_entry.score = new_score
            existing_entry.level = float(overall_score) if overall_score else 0
            existing_entry.improvement_percentage = improvement_percentage
            existing_entry.last_scan_at = datetime.utcnow()
            existing_entry.scans_count = (existing_entry.scans_count or 0) + 1
        else:
            new_entry = Leaderboard(
                user_id=user_uuid,
                score=leaderboard_score,
                level=float(overall_score) if overall_score else 0,
                streak_days=1,
                improvement_percentage=improvement_percentage,
                scans_count=1,
                last_scan_at=datetime.utcnow()
            )
            db.add(new_entry)

        await db.commit()

        # Recalculate ranks for all leaderboard entries
        all_entries_result = await db.execute(
            select(Leaderboard).order_by(Leaderboard.score.desc())
        )
        all_entries = all_entries_result.scalars().all()
        for rank, entry in enumerate(all_entries, 1):
            entry.rank = rank
        await db.commit()

        return {"message": "Analysis complete", "scan_id": scan_id}

    except Exception as e:
        scan.processing_status = "failed"
        scan.analysis = {"error_message": str(e)}
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.get("/latest")
async def get_latest_scan(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get most recent scan"""
    user_uuid = UUID(current_user["id"])

    result = await db.execute(
        select(Scan)
        .where(Scan.user_id == user_uuid)
        .order_by(Scan.created_at.desc())
        .limit(1)
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
        "processing_status": scan.processing_status
    }

    if scan.analysis:
        if is_paid:
            response["analysis"] = scan.analysis
        else:
            # For unpaid users, only show overall score
            a = scan.analysis
            overall_score = a.get("scan_summary", {}).get("overall_score")
            if overall_score is None:
                overall_score = a.get("metrics", {}).get("overall_score")
            if overall_score is None:
                overall_score = a.get("overall_score", 0)
            response["analysis"] = {"overall_score": overall_score, "locked": True}

    return response


@router.get("/history")
async def get_scan_history(
    limit: int = 10,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db)
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
        score = a.get("scan_summary", {}).get("overall_score")
        if score is None:
            score = a.get("metrics", {}).get("overall_score")
        if score is None:
            score = a.get("overall_score", 0)
        scans.append({"id": str(s.id), "created_at": s.created_at, "overall_score": score})

    return {"scans": scans}


@router.get("/{scan_id}")
async def get_scan_by_id(
    scan_id: str,
    current_user: dict = Depends(require_paid_user),
    db: AsyncSession = Depends(get_db)
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
        "processing_status": scan.processing_status
    }


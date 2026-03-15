from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
    db: AsyncSession = Depends(get_db),
):
    """Upload a 15-second face scan video and analyze directly"""
    user_uuid = UUID(current_user["id"])

    video_data = await video.read()
    if not video_data:
        raise HTTPException(status_code=400, detail="No video data received")

    scan_row = Scan(
        user_id=user_uuid,
        created_at=datetime.utcnow(),
        is_unlocked=current_user.get("is_paid", False),
        processing_status="processing",
        scan_type="video",
    )
    db.add(scan_row)
    await db.commit()
    await db.refresh(scan_row)
    scan_id = str(scan_row.id)

    try:
        analysis = await facial_analysis_client.upload_video(video_data)

        scan_row.analysis = analysis
        scan_row.processing_status = "completed"
        await db.commit()

        user = await db.get(User, user_uuid)
        if user and not user.first_scan_completed:
            user.first_scan_completed = True
            await db.commit()

        # Update leaderboard
        overall_score = 0.0
        if isinstance(analysis, dict):
            overall_score = analysis.get("scan_summary", {}).get("overall_score")
            if overall_score is None:
                overall_score = analysis.get("metrics", {}).get("overall_score")
            if overall_score is None:
                overall_score = analysis.get("overall_score", 0.0)

        leaderboard_score = (float(overall_score) if overall_score else 0) * 10

        leaderboard_result = await db.execute(
            select(Leaderboard).where(Leaderboard.user_id == user_uuid)
        )
        entry = leaderboard_result.scalar_one_or_none()

        if entry:
            entry.score = max(entry.score or 0, leaderboard_score)
            entry.level = float(overall_score) if overall_score else 0
            entry.last_scan_at = datetime.utcnow()
            entry.scans_count = (entry.scans_count or 0) + 1
        else:
            entry = Leaderboard(
                user_id=user_uuid,
                score=leaderboard_score,
                level=float(overall_score) if overall_score else 0,
                streak_days=1,
                improvement_percentage=0,
                scans_count=1,
                last_scan_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
            )
            db.add(entry)

        await db.commit()

        # Recalculate ranks
        all_entries_result = await db.execute(
            select(Leaderboard).order_by(Leaderboard.score.desc())
        )
        all_entries = all_entries_result.scalars().all()
        for rank, e in enumerate(all_entries, 1):
            e.rank = rank
        await db.commit()

        # Send WhatsApp notification (non-blocking)
        try:
            if user and user.phone_number:
                from services.twilio_service import twilio_service
                import asyncio
                asyncio.create_task(twilio_service.send_scan_complete(
                    user.phone_number,
                    user.email or "",
                    float(overall_score) if overall_score else None
                ))
        except Exception as notif_err:
            import logging
            logging.getLogger(__name__).warning(f"Scan notification failed: {notif_err}")

        return {"scan_id": scan_id, "analysis": analysis}

    except Exception as e:
        scan_row.processing_status = "failed"
        scan_row.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.post("/realtime")
async def analyze_realtime_scan(
    payload: RealtimeScanRequest,
    current_user: dict = Depends(get_current_user),
):
    """Proxy to realtime analysis endpoint"""
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
    db: AsyncSession = Depends(get_db),
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

    if scan.scan_type == "video":
        if scan.processing_status == "completed":
            return {"message": "Analysis already completed", "scan_id": scan_id}
        raise HTTPException(status_code=400, detail="Video scans are analyzed during upload")

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

        analysis = await facial_analysis_client.analyze_frames([front_data, left_data, right_data])

        scan.analysis = analysis
        scan.processing_status = "completed"
        await db.commit()

        overall_score = 0.0
        if isinstance(analysis, dict):
            overall_score = analysis.get("scan_summary", {}).get("overall_score")
            if overall_score is None:
                overall_score = analysis.get("metrics", {}).get("overall_score")
            if overall_score is None:
                overall_score = analysis.get("overall_score", 0.0)

        # Calculate improvement percentage
        scans_result = await db.execute(
            select(Scan)
            .where((Scan.user_id == user_uuid) & (Scan.processing_status == "completed"))
            .order_by(Scan.created_at.desc())
        )
        user_scans = scans_result.scalars().all()
        scores = []
        for s in user_scans:
            a = s.analysis or {}
            score = a.get("scan_summary", {}).get("overall_score")
            if score is None:
                score = a.get("metrics", {}).get("overall_score")
            if score is None:
                score = a.get("overall_score", 0)
            scores.append(score)

        improvement_percentage = 0
        if len(scores) >= 2:
            first_score = scores[-1] or 0
            latest_score = scores[0] or 0
            if first_score > 0:
                improvement_percentage = ((latest_score - first_score) / first_score) * 100

        leaderboard_score = (float(overall_score) if overall_score else 0) * 10
        leaderboard_result = await db.execute(
            select(Leaderboard).where(Leaderboard.user_id == user_uuid)
        )
        entry = leaderboard_result.scalar_one_or_none()

        if entry:
            entry.score = max(entry.score or 0, leaderboard_score)
            entry.level = float(overall_score) if overall_score else 0
            entry.improvement_percentage = improvement_percentage
            entry.last_scan_at = datetime.utcnow()
            entry.scans_count = (entry.scans_count or 0) + 1
        else:
            entry = Leaderboard(
                user_id=user_uuid,
                score=leaderboard_score,
                level=float(overall_score) if overall_score else 0,
                streak_days=1,
                improvement_percentage=improvement_percentage,
                scans_count=1,
                last_scan_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
            )
            db.add(entry)

        await db.commit()

        all_entries_result = await db.execute(
            select(Leaderboard).order_by(Leaderboard.score.desc())
        )
        all_entries = all_entries_result.scalars().all()
        for rank, e in enumerate(all_entries, 1):
            e.rank = rank
        await db.commit()

        return {"message": "Analysis complete", "scan_id": scan_id}

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
    }

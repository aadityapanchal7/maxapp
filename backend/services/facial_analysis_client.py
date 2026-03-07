"""
Facial Analysis Client
Direct HTTP client for the cannon_facial_analysis microservice.
No LangGraph, no Gemini — pure HTTP proxy.
"""

import httpx
import base64
import time
import io
from typing import List, Dict, Any, Optional
from config import settings
from models.scan import (
    ScanAnalysis
)


class FacialAnalysisClient:
    """
    HTTP client for the cannon_facial_analysis service.

    Supports multiple call modes:
      1. upload_video(video_bytes)   → POST /scan/upload-video   (multipart)
      2. analyze_frames(frames)     → POST /scan/analyze         (JSON base64)
      3. analyze_realtime(image)    → POST /scan/analyze-realtime (JSON base64)
    """

    def __init__(self):
        self.base_url = settings.facial_analysis_api_url  # e.g. http://localhost:8001/api
        self.timeout = 120.0  # video analysis can take a while

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def upload_video(self, video_bytes: bytes, filename: str = "scan.mp4") -> Dict[str, Any]:
        """
        Send a raw video file to /scan/upload-video and return the JSON dict.
        This is the primary endpoint used by the mobile app flow.
        """
        url = f"{self.base_url}/scan/upload-video"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                files = {"file": (filename, io.BytesIO(video_bytes), "video/mp4")}
                response = await client.post(url, files=files)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                detail = e.response.text if e.response else str(e)
                print(f"[FacialAnalysisClient] HTTP error from analysis service: {detail}")
                return self._create_error_analysis(f"Analysis service returned {e.response.status_code}: {detail}")
            except Exception as e:
                print(f"[FacialAnalysisClient] Error calling analysis service: {e}")
                return self._create_error_analysis(str(e))

    async def analyze_frames(self, frames_data: List[bytes]) -> Dict[str, Any]:
        """
        Send a list of JPEG frame bytes to /scan/analyze (JSON payload).
        Used when frames have already been extracted from a video.
        """
        url = f"{self.base_url}/scan/analyze"

        frames = []
        for i, frame_bytes in enumerate(frames_data):
            b64 = base64.b64encode(frame_bytes).decode("utf-8")
            frames.append({
                "image": f"data:image/jpeg;base64,{b64}",
                "timestamp": time.time() + (i * 0.1)
            })

        payload = {"frames": frames, "config": {}}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                detail = e.response.text if e.response else str(e)
                print(f"[FacialAnalysisClient] HTTP error from analysis service: {detail}")
                return self._create_error_analysis(f"Analysis service returned {e.response.status_code}: {detail}")
            except Exception as e:
                print(f"[FacialAnalysisClient] Error calling analysis service: {e}")
                return self._create_error_analysis(str(e))

    async def analyze_realtime(self, image_data_url: str, include_visuals: bool = True,
                               timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Proxy to /scan/analyze-realtime for live overlay + guidance.

        image_data_url should be a full data URL string, e.g. "data:image/jpeg;base64,...."
        This matches what the cannon_facial_analysis frontend sends today.
        """
        url = f"{self.base_url}/scan/analyze-realtime"
        payload = {
            "image": image_data_url,
            "include_visuals": include_visuals,
            "timestamp": timestamp or time.time(),
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                detail = e.response.text if e.response else str(e)
                print(f"[FacialAnalysisClient] HTTP error (realtime): {detail}")
                # Shape this like the realtime API response so callers can handle gracefully
                return {
                    "success": False,
                    "detected_angle": "unknown",
                    "angle_confidence": 0.0,
                    "quality_score": 0.0,
                    "feedback": {"message": "Realtime analysis HTTP error", "error": detail},
                    "landmarks_detected": False,
                    "processed_image": None,
                }
            except Exception as e:
                print(f"[FacialAnalysisClient] Error calling realtime analysis service: {e}")
                return {
                    "success": False,
                    "detected_angle": "unknown",
                    "angle_confidence": 0.0,
                    "quality_score": 0.0,
                    "feedback": {"message": "Realtime analysis failed", "error": str(e)},
                    "landmarks_detected": False,
                    "processed_image": None,
                }

    async def health_check(self) -> bool:
        """Returns True if the cannon_facial_analysis service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    def _create_error_analysis(self, error_msg: str) -> Dict[str, Any]:
        """Return a minimal valid dict when the service call fails."""
        return {
            "success": False,
            "error": error_msg,
            "scan_summary": {"overall_score": 0.0},
            "ai_recommendations": {
                "summary": f"Analysis service unavailable: {error_msg}",
                "recommendations": []
            }
        }


# Singleton
facial_analysis_client = FacialAnalysisClient()

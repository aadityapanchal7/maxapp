"""
LangGraph Workflow for Face Analysis
Multi-step agent pipeline with structured outputs and fallbacks
Compatible with langgraph 0.0.26
"""

import asyncio
from typing import TypedDict, Optional, List
import google.generativeai as genai
from pydantic import BaseModel, Field
from config import settings
from services.llm_provider import use_openai
from services.langgraph_face_prompts import (
    LANGGRAPH_ANALYZE_FACE_METRICS_FALLBACK,
    LANGGRAPH_IMPROVEMENTS_FALLBACK,
    LANGGRAPH_VALIDATE_IMAGES_FALLBACK,
)
from services.prompt_loader import PromptKey, resolve_prompt
from models.scan import (
    ScanAnalysis, FaceMetrics, ImprovementSuggestion, ImprovementPriority,
    JawlineMetrics, CheekbonesMetrics, EyeAreaMetrics, NoseMetrics,
    LipsMetrics, ForeheadMetrics, SkinMetrics, FacialProportions,
    ProfileMetrics, HairMetrics, BodyFatIndicators
)
import json
import cv2
import tempfile
import os
import numpy as np


if not use_openai():
    genai.configure(api_key=settings.gemini_api_key)


# ============================================
# STATE DEFINITIONS
# ============================================

class ImageValidationResult(BaseModel):
    """Result of image validation step"""
    is_valid: bool = True
    front_quality: float = Field(default=7.0, ge=0, le=10)
    left_quality: float = Field(default=7.0, ge=0, le=10)
    right_quality: float = Field(default=7.0, ge=0, le=10)
    face_detected_front: bool = True
    face_detected_left: bool = True
    face_detected_right: bool = True
    issues: List[str] = Field(default_factory=list)


class GraphState(TypedDict):
    """State for the workflow"""
    front_image: bytes
    left_image: bytes
    right_image: bytes
    validation_result: Optional[dict]
    face_metrics: Optional[dict]
    improvements: Optional[list]
    course_mappings: Optional[list]
    analysis: Optional[dict]
    error: Optional[str]
    retry_count: int


# ============================================
# ANALYSIS FUNCTIONS
# ============================================

async def validate_images(state: GraphState) -> GraphState:
    """Step 1: Validate image quality and detect faces"""
    try:
        validation_prompt = await asyncio.to_thread(
            resolve_prompt,
            PromptKey.LANGGRAPH_VALIDATE_IMAGES,
            LANGGRAPH_VALIDATE_IMAGES_FALLBACK,
        )

        if use_openai():
            from services.openai_service import openai_service

            text = await openai_service.completion_vision(
                validation_prompt,
                [state["front_image"], state["left_image"], state["right_image"]],
                json_mode=True,
            )
        else:
            model = genai.GenerativeModel(settings.gemini_model)
            response = model.generate_content([
                validation_prompt,
                {"mime_type": "image/jpeg", "data": state["front_image"]},
                {"mime_type": "image/jpeg", "data": state["left_image"]},
                {"mime_type": "image/jpeg", "data": state["right_image"]},
            ])
            text = response.text.strip()

        if text.startswith("```"):
            text = text.split("```")[1].replace("json", "").strip()
        
        validation_data = json.loads(text)
        return {**state, "validation_result": validation_data, "error": None}
        
    except Exception as e:
        fallback_result = {"is_valid": True, "front_quality": 7.0, "left_quality": 7.0, "right_quality": 7.0, "issues": []}
        return {**state, "validation_result": fallback_result, "error": str(e)}


async def analyze_face_metrics(state: GraphState) -> GraphState:
    """Step 2: Detailed face analysis"""
    try:
        model = genai.GenerativeModel(settings.gemini_model)

        analysis_prompt = await asyncio.to_thread(
            resolve_prompt,
            PromptKey.LANGGRAPH_ANALYZE_FACE_METRICS,
            LANGGRAPH_ANALYZE_FACE_METRICS_FALLBACK,
        )

        response = model.generate_content([
            analysis_prompt,
            {"mime_type": "image/jpeg", "data": state["front_image"]},
            {"mime_type": "image/jpeg", "data": state["left_image"]},
            {"mime_type": "image/jpeg", "data": state["right_image"]},
        ])
        
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].replace("json", "").strip()
        
        metrics_data = json.loads(text)
        
        # Add image quality from validation
        validation = state.get("validation_result", {})
        metrics_data["image_quality_front"] = validation.get("front_quality", 7.0)
        metrics_data["image_quality_left"] = validation.get("left_quality", 7.0)
        metrics_data["image_quality_right"] = validation.get("right_quality", 7.0)
        
        return {**state, "face_metrics": metrics_data, "error": None}
        
    except Exception as e:
        retry_count = state.get("retry_count", 0)
        if retry_count < 2:
            return {**state, "error": str(e), "retry_count": retry_count  1}
        return {**state, "face_metrics": create_default_metrics_dict(), "error": f"Analysis failed: {e}"}


async def generate_improvements(state: GraphState) -> GraphState:
    """Step 3: Generate improvement suggestions"""
    try:
        metrics = state.get("face_metrics")
        if not metrics:
            return {**state, "improvements": [], "error": "No metrics available"}
        
        tmpl = await asyncio.to_thread(
            resolve_prompt,
            PromptKey.LANGGRAPH_IMPROVEMENTS,
            LANGGRAPH_IMPROVEMENTS_FALLBACK,
        )
        improvement_prompt = tmpl.format(overall_score=metrics.get("overall_score", 5))

        if use_openai():
            from services.openai_service import openai_service

            text = await openai_service.completion_text(improvement_prompt)
        else:
            model = genai.GenerativeModel(settings.gemini_model)
            response = model.generate_content(improvement_prompt)
            text = response.text.strip()

        if text.startswith("```"):
            text = text.split("```")[1].replace("json", "").strip()
        
        improvements = json.loads(text)
        return {**state, "improvements": improvements, "error": None}
        
    except Exception as e:
        return {**state, "improvements": [], "error": str(e)}


async def map_to_courses(state: GraphState) -> GraphState:
    """Step 4: Map improvements to courses"""
    try:
        improvements = state.get("improvements", [])
        
        course_map = {
            "jawline": "jawline-mastery",
            "jaw": "jawline-mastery",
            "skin": "skincare-essentials",
            "fat": "fat-loss-for-face",
            "body": "fat-loss-for-face",
            "hair": "hair-optimization",
            "posture": "posture-correction",
        }
        
        recommended = set()
        for imp in improvements:
            area_lower = imp.get("area", "").lower()
            for keyword, course in course_map.items():
                if keyword in area_lower:
                    recommended.add(course)
        
        return {**state, "course_mappings": list(recommended)}
        
    except Exception as e:
        return {**state, "course_mappings": [], "error": str(e)}


async def compile_analysis(state: GraphState) -> GraphState:
    """Step 5: Compile final analysis"""
    try:
        metrics = state.get("face_metrics", {})
        improvements = state.get("improvements", [])
        courses = state.get("course_mappings", [])
        
        # Identify strengths and focus areas
        strengths = []
        focus_areas = []
        
        if metrics.get("jawline", {}).get("definition_score", 0) >= 7:
            strengths.append("Well-defined jawline")
        else:
            focus_areas.append("Jawline definition")
        
        if metrics.get("skin", {}).get("overall_quality", 0) >= 7:
            strengths.append("Good skin quality")
        else:
            focus_areas.append("Skin improvement")
        
        if metrics.get("proportions", {}).get("overall_symmetry", 0) >= 7:
            strengths.append("Good facial symmetry")
        
        overall = metrics.get("overall_score", 5)
        potential = min(10.0, overall  len(focus_areas) * 0.5)
        
        analysis = {
            "metrics": metrics,
            "improvements": improvements,
            "top_strengths": strengths[:5],
            "focus_areas": focus_areas[:5],
            "recommended_courses": courses,
            "personalized_summary": f"Your overall score is {overall}/10. With consistent effort on your focus areas, you could reach {potential:.1f}/10.",
            "estimated_potential": potential
        }
        
        return {**state, "analysis": analysis}
        
    except Exception as e:
        return {**state, "analysis": {"error": str(e)}, "error": str(e)}


def create_default_metrics_dict() -> dict:
    """Create default metrics for fallback"""
    return {
        "overall_score": 5.0,
        "harmony_score": 5.0,
        "jawline": {"definition_score": 5, "symmetry_score": 5, "masseter_development": 5, "chin_projection": 5, "ramus_length": 5},
        "cheekbones": {"prominence_score": 5, "width_score": 5, "hollowness_below": 5, "symmetry_score": 5},
        "eye_area": {"upper_eyelid_exposure": 5, "palpebral_fissure_height": 5, "under_eye_area": 5, "brow_bone_prominence": 5, "orbital_rim_support": 5, "symmetry_score": 5},
        "nose": {"bridge_height": 5, "tip_projection": 5, "nostril_symmetry": 5, "overall_harmony": 5},
        "lips": {"upper_lip_volume": 5, "lower_lip_volume": 5, "cupids_bow_definition": 5, "vermillion_border": 5, "philtrum_definition": 5, "lip_symmetry": 5},
        "forehead": {"brow_bone_projection": 5, "temple_hollowing": 5, "forehead_symmetry": 5, "skin_texture": 5},
        "skin": {"overall_quality": 5, "texture_score": 5, "clarity_score": 5, "tone_evenness": 5, "hydration_appearance": 5, "pore_visibility": 5, "under_eye_darkness": 5},
        "proportions": {"facial_thirds_balance": 5, "upper_third_score": 5, "middle_third_score": 5, "lower_third_score": 5, "horizontal_fifths_balance": 5, "overall_symmetry": 5, "facial_convexity": 5, "golden_ratio_adherence": 5},
        "profile": {"forehead_projection": 5, "nose_projection": 5, "lip_projection": 5, "chin_projection": 5, "submental_area": 5, "ramus_visibility": 5, "profile_harmony": 5},
        "hair": {"density": 5, "hairline_health": 5, "hair_quality": 5},
        "body_fat": {"facial_leanness": 5, "definition_potential": 5},
        "confidence_score": 0.5,
        "image_quality_front": 5.0,
        "image_quality_left": 5.0,
        "image_quality_right": 5.0
    }


# ============================================
# SIMPLE PIPELINE (No LangGraph dependency issues)
# ============================================

async def run_face_analysis_pipeline(front_image: bytes, left_image: bytes, right_image: bytes) -> ScanAnalysis:
    """Run the complete face analysis pipeline"""
    
    state: GraphState = {
        "front_image": front_image,
        "left_image": left_image,
        "right_image": right_image,
        "validation_result": None,
        "face_metrics": None,
        "improvements": None,
        "course_mappings": None,
        "analysis": None,
        "error": None,
        "retry_count": 0
    }
    
    # Run pipeline steps
    state = await validate_images(state)
    state = await analyze_face_metrics(state)
    state = await generate_improvements(state)
    state = await map_to_courses(state)
    state = await compile_analysis(state)
    
    # Convert to ScanAnalysis
    analysis_data = state.get("analysis", {})
    
    try:
        return ScanAnalysis(
            metrics=build_face_metrics(analysis_data.get("metrics", {})),
            improvements=[build_improvement(imp) for imp in analysis_data.get("improvements", [])],
            top_strengths=analysis_data.get("top_strengths", []),
            focus_areas=analysis_data.get("focus_areas", []),
            recommended_courses=analysis_data.get("recommended_courses", []),
            personalized_summary=analysis_data.get("personalized_summary", ""),
            estimated_potential=analysis_data.get("estimated_potential", 5.0)
        )
    except Exception as e:
        return create_fallback_analysis(str(e))


def extract_frames_from_video(video_data: bytes) -> tuple[bytes, bytes, bytes]:
    """Extract front, left, and right profile frames from video"""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        tf.write(video_data)
        video_path = tf.name
    
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        
        # Guide: Front (0s), Left (~4-5s), Back to Front (~8-10s), Right (~13-15s)
        # We sample: Front (0.5s), Left (5s), Right (14s)
        indices = [
            int(0.5 * fps),    # Front
            int(5.0 * fps),    # Left
            int(14.0 * fps)    # Right
        ]
        
        frames = []
        for idx in indices:
            # Clamp to video length
            safe_idx = min(idx, total_frames - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, safe_idx)
            success, frame = cap.read()
            if success:
                # Convert to JPEG
                _, buffer = cv2.imencode('.jpg', frame)
                frames.append(buffer.tobytes())
            else:
                # Fallback to first frame if seek fails
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                _, frame = cap.read()
                _, buffer = cv2.imencode('.jpg', frame)
                frames.append(buffer.tobytes())
        
        # Ensure we have 3 frames
        while len(frames) < 3:
            frames.append(frames[-1] if frames else b"")
            
        return frames[0], frames[1], frames[2]
        
    finally:
        cap.release()
        if os.path.exists(video_path):
            os.remove(video_path)


async def run_video_analysis_pipeline(video_data: bytes) -> ScanAnalysis:
    """Extract frames from video and run analysis pipeline"""
    try:
        front, left, right = extract_frames_from_video(video_data)
        return await run_face_analysis_pipeline(front, left, right)
    except Exception as e:
        return create_fallback_analysis(f"Video extraction failed: {str(e)}")


def build_face_metrics(data: dict) -> FaceMetrics:
    """Build FaceMetrics from dict"""
    return FaceMetrics(
        overall_score=data.get("overall_score", 5.0),
        harmony_score=data.get("harmony_score", 5.0),
        jawline=JawlineMetrics(**{k: data.get("jawline", {}).get(k, 5) for k in ["definition_score", "symmetry_score", "masseter_development", "chin_projection", "ramus_length"]}),
        cheekbones=CheekbonesMetrics(**{k: data.get("cheekbones", {}).get(k, 5) for k in ["prominence_score", "width_score", "hollowness_below", "symmetry_score"]}),
        eye_area=EyeAreaMetrics(**{k: data.get("eye_area", {}).get(k, 5) for k in ["upper_eyelid_exposure", "palpebral_fissure_height", "under_eye_area", "brow_bone_prominence", "orbital_rim_support", "symmetry_score"]}),
        nose=NoseMetrics(**{k: data.get("nose", {}).get(k, 5) for k in ["bridge_height", "tip_projection", "nostril_symmetry", "overall_harmony"]}),
        lips=LipsMetrics(**{k: data.get("lips", {}).get(k, 5) for k in ["upper_lip_volume", "lower_lip_volume", "cupids_bow_definition", "vermillion_border", "philtrum_definition", "lip_symmetry"]}),
        forehead=ForeheadMetrics(**{k: data.get("forehead", {}).get(k, 5) for k in ["brow_bone_projection", "temple_hollowing", "forehead_symmetry", "skin_texture"]}),
        skin=SkinMetrics(**{k: data.get("skin", {}).get(k, 5) for k in ["overall_quality", "texture_score", "clarity_score", "tone_evenness", "hydration_appearance", "pore_visibility", "under_eye_darkness"]}),
        proportions=FacialProportions(**{k: data.get("proportions", {}).get(k, 5) for k in ["facial_thirds_balance", "upper_third_score", "middle_third_score", "lower_third_score", "horizontal_fifths_balance", "overall_symmetry", "facial_convexity", "golden_ratio_adherence"]}),
        profile=ProfileMetrics(**{k: data.get("profile", {}).get(k, 5) for k in ["forehead_projection", "nose_projection", "lip_projection", "chin_projection", "submental_area", "ramus_visibility", "profile_harmony"]}),
        hair=HairMetrics(**{k: data.get("hair", {}).get(k, 5) for k in ["density", "hairline_health", "hair_quality"]}),
        body_fat=BodyFatIndicators(**{k: data.get("body_fat", {}).get(k, 5) for k in ["facial_leanness", "definition_potential"]}),
        confidence_score=data.get("confidence_score", 0.5),
        image_quality_front=data.get("image_quality_front", 5.0),
        image_quality_left=data.get("image_quality_left", 5.0),
        image_quality_right=data.get("image_quality_right", 5.0)
    )


def build_improvement(data: dict) -> ImprovementSuggestion:
    """Build ImprovementSuggestion from dict"""
    priority_map = {"high": ImprovementPriority.HIGH, "medium": ImprovementPriority.MEDIUM, "low": ImprovementPriority.LOW}
    return ImprovementSuggestion(
        area=data.get("area", "general"),
        priority=priority_map.get(data.get("priority", "medium"), ImprovementPriority.MEDIUM),
        current_score=data.get("current_score", 5),
        potential_score=data.get("potential_score", 7),
        suggestion=data.get("suggestion", ""),
        exercises=data.get("exercises", []),
        products=data.get("products", []),
        timeframe=data.get("timeframe", "")
    )


def create_fallback_analysis(error: str) -> ScanAnalysis:
    """Create fallback analysis on error"""
    return ScanAnalysis(
        metrics=build_face_metrics(create_default_metrics_dict()),
        improvements=[],
        top_strengths=[],
        focus_areas=["Retry analysis"],
        recommended_courses=[],
        personalized_summary=f"Analysis encountered an issue. Please try again. Error: {error}",
        estimated_potential=5.0
    )

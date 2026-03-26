"""Fallback LLM prompts for agents/langgraph_workflow.py (no heavy deps). Override via S3 keys langgraph_*."""

LANGGRAPH_VALIDATE_IMAGES_FALLBACK = """Analyze these three face photos and validate them.
For each image assess: face visibility and image quality (0-10).

Return JSON:
{"is_valid": true, "front_quality": 8, "left_quality": 7, "right_quality": 7, "issues": []}

ONLY return JSON, no other text."""

LANGGRAPH_ANALYZE_FACE_METRICS_FALLBACK = """You are an expert facial aesthetics analyst. Analyze these photos comprehensively.

Provide scores 0-10 for ALL metrics. Return a complete JSON with this structure:
{
  "overall_score": 6.5,
  "harmony_score": 6.0,
  "jawline": {"definition_score": 6, "symmetry_score": 7, "masseter_development": 5, "chin_projection": 6, "ramus_length": 6},
  "cheekbones": {"prominence_score": 6, "width_score": 6, "hollowness_below": 5, "symmetry_score": 7},
  "eye_area": {"upper_eyelid_exposure": 5, "palpebral_fissure_height": 6, "under_eye_area": 6, "brow_bone_prominence": 5, "orbital_rim_support": 6, "symmetry_score": 7},
  "nose": {"bridge_height": 6, "tip_projection": 6, "nostril_symmetry": 7, "overall_harmony": 6},
  "lips": {"upper_lip_volume": 6, "lower_lip_volume": 6, "cupids_bow_definition": 6, "vermillion_border": 6, "philtrum_definition": 6, "lip_symmetry": 7},
  "forehead": {"brow_bone_projection": 5, "temple_hollowing": 6, "forehead_symmetry": 7, "skin_texture": 6},
  "skin": {"overall_quality": 6, "texture_score": 6, "clarity_score": 6, "tone_evenness": 6, "hydration_appearance": 6, "pore_visibility": 6, "under_eye_darkness": 6},
  "proportions": {"facial_thirds_balance": 6, "upper_third_score": 6, "middle_third_score": 6, "lower_third_score": 6, "horizontal_fifths_balance": 6, "overall_symmetry": 7, "facial_convexity": 6, "golden_ratio_adherence": 6},
  "profile": {"forehead_projection": 6, "nose_projection": 6, "lip_projection": 6, "chin_projection": 6, "submental_area": 6, "ramus_visibility": 6, "profile_harmony": 6},
  "hair": {"density": 7, "hairline_health": 6, "hair_quality": 6},
  "body_fat": {"facial_leanness": 6, "definition_potential": 7},
  "confidence_score": 0.8
}

Be thorough and honest. ONLY return JSON, no markdown or explanations."""

# After load from S3: .format(overall_score=...). JSON braces in example are escaped as {{ }}
LANGGRAPH_IMPROVEMENTS_FALLBACK = """Based on face analysis with overall score {overall_score}/10, generate improvement suggestions.

Return JSON array:
[{{"area": "jawline", "priority": "high", "current_score": 5, "potential_score": 7, "suggestion": "Practice mewing and jaw exercises", "exercises": ["Mewing", "Chewing gum"], "products": [], "timeframe": "3-6 months"}}]

Focus on areas with scores below 7. ONLY return JSON array."""

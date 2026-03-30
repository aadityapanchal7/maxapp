"""
Face Scan Models - Structured outputs for AI analysis
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum


class FaceShape(str, Enum):
    """Detected face shape types"""
    OVAL = "oval"
    ROUND = "round"
    SQUARE = "square"
    HEART = "heart"
    OBLONG = "oblong"
    DIAMOND = "diamond"
    TRIANGLE = "triangle"


class SkinType(str, Enum):
    """Skin type classification"""
    NORMAL = "normal"
    OILY = "oily"
    DRY = "dry"
    COMBINATION = "combination"
    SENSITIVE = "sensitive"


class ImprovementPriority(str, Enum):
    """Priority levels for improvements"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ============================================
# EXHAUSTIVE FACE METRICS - STRUCTURED OUTPUT
# ============================================

class JawlineMetrics(BaseModel):
    """Detailed jawline analysis"""
    definition_score: float = Field(ge=0, le=10, description="Overall jawline definition clarity")
    angle_degrees: Optional[float] = Field(default=None, description="Gonial angle in degrees (ideal: 120-130)")
    symmetry_score: float = Field(ge=0, le=10, description="Left-right jawline symmetry")
    width_ratio: Optional[float] = Field(default=None, description="Jaw width to face width ratio")
    masseter_development: float = Field(ge=0, le=10, description="Masseter muscle visibility/development")
    chin_projection: float = Field(ge=0, le=10, description="Chin forward projection score")
    chin_shape: str = Field(default="average", description="Chin shape: pointed, square, round, cleft")
    ramus_length: float = Field(ge=0, le=10, description="Vertical ramus length assessment")
    notes: str = Field(default="", description="Additional observations")


class CheekbonesMetrics(BaseModel):
    """Cheekbone analysis"""
    prominence_score: float = Field(ge=0, le=10, description="Cheekbone visibility/projection")
    height_position: str = Field(default="medium", description="Position: high, medium, low")
    width_score: float = Field(ge=0, le=10, description="Bizygomatic width assessment")
    hollowness_below: float = Field(ge=0, le=10, description="Hollow beneath cheekbones (buccal area)")
    symmetry_score: float = Field(ge=0, le=10, description="Left-right cheekbone symmetry")
    notes: str = Field(default="", description="Additional observations")


class EyeAreaMetrics(BaseModel):
    """Comprehensive eye area analysis"""
    canthal_tilt: str = Field(default="neutral", description="positive, neutral, or negative tilt")
    canthal_tilt_degrees: Optional[float] = Field(default=None, description="Tilt angle in degrees")
    interpupillary_distance: str = Field(default="average", description="close, average, wide")
    eye_spacing_ratio: Optional[float] = Field(default=None, description="Eye spacing to eye width ratio")
    upper_eyelid_exposure: float = Field(ge=0, le=10, description="Upper eyelid visibility (lower is often better)")
    palpebral_fissure_height: float = Field(ge=0, le=10, description="Eye opening height assessment")
    eye_shape: str = Field(default="almond", description="almond, round, hooded, monolid, downturned, upturned")
    under_eye_area: float = Field(ge=0, le=10, description="Under-eye health (hollows, bags, dark circles)")
    eyebrow_position: str = Field(default="neutral", description="Position relative to brow bone")
    eyebrow_shape: str = Field(default="natural", description="Shape assessment")
    brow_bone_prominence: float = Field(ge=0, le=10, description="Brow ridge projection")
    orbital_rim_support: float = Field(ge=0, le=10, description="Infraorbital support assessment")
    symmetry_score: float = Field(ge=0, le=10, description="Overall eye area symmetry")
    notes: str = Field(default="", description="Additional observations")


class NoseMetrics(BaseModel):
    """Nose analysis"""
    dorsum_shape: str = Field(default="straight", description="straight, convex, concave, wavy")
    bridge_width: str = Field(default="average", description="narrow, average, wide")
    bridge_height: float = Field(ge=0, le=10, description="Nasal bridge height/projection")
    tip_shape: str = Field(default="normal", description="refined, bulbous, droopy, upturned")
    tip_projection: float = Field(ge=0, le=10, description="Nasal tip projection")
    tip_rotation: str = Field(default="neutral", description="up-rotated, neutral, down-rotated")
    nostril_shape: str = Field(default="oval", description="Nostril shape assessment")
    nostril_symmetry: float = Field(ge=0, le=10, description="Nostril symmetry score")
    alar_width: str = Field(default="proportional", description="narrow, proportional, wide")
    nasofrontal_angle: Optional[float] = Field(default=None, description="Angle at nasion in degrees")
    nasolabial_angle: Optional[float] = Field(default=None, description="Nose-lip angle in degrees")
    overall_harmony: float = Field(ge=0, le=10, description="Nose harmony with face")
    notes: str = Field(default="", description="Additional observations")


class LipsMetrics(BaseModel):
    """Lips and mouth analysis"""
    upper_lip_volume: float = Field(ge=0, le=10, description="Upper lip fullness")
    lower_lip_volume: float = Field(ge=0, le=10, description="Lower lip fullness")
    lip_ratio: Optional[float] = Field(default=None, description="Upper to lower lip ratio (ideal ~1:1.6)")
    cupids_bow_definition: float = Field(ge=0, le=10, description="Cupid's bow clarity")
    lip_width: str = Field(default="proportional", description="narrow, proportional, wide")
    vermillion_border: float = Field(ge=0, le=10, description="Lip border definition")
    mouth_width_ratio: Optional[float] = Field(default=None, description="Mouth to nose width ratio")
    philtrum_length: str = Field(default="average", description="short, average, long")
    philtrum_definition: float = Field(ge=0, le=10, description="Philtrum column clarity")
    notes: str = Field(default="", description="Additional observations")


# ============================================
# NEW DETAILED MEASUREMENT MODELS
# ============================================

class MeasurementDetail(BaseModel):
    """Specific measurement with value, score and optional rating"""
    value: float
    score: Optional[float] = None
    rating: Optional[str] = None

class AdvancedMeasurements(BaseModel):
    """Grouped measurements by view"""
    front_view: Dict[str, MeasurementDetail]
    profile_view: Dict[str, MeasurementDetail]

class AdvancedScanSummary(BaseModel):
    """Summary of the scan process"""
    overall_score: float
    frames_analyzed: Optional[int] = None
    total_frames: Optional[int] = None
    frames_by_angle: Dict[str, int]

class AdvancedAIRecommendations(BaseModel):
    """Structured AI feedback"""
    summary: str
    strengths: List[str]
    recommendations: List[Dict[str, str]]

class GoldenRatioAnalysis(BaseModel):
    """Details of golden ratio adherence"""
    average_score: float
    scores: Dict[str, float]

class AdvancedAnalysis(BaseModel):
    """Root model for the new comprehensive analysis format"""
    success: bool = True
    scan_summary: AdvancedScanSummary
    measurements: AdvancedMeasurements
    golden_ratio_analysis: GoldenRatioAnalysis
    ai_recommendations: AdvancedAIRecommendations
    processed_image: Optional[str] = None # Base64 visualization


class ForeheadMetrics(BaseModel):
    """Forehead analysis"""
    height: str = Field(default="average", description="short, average, tall")
    width: str = Field(default="proportional", description="narrow, proportional, wide")
    shape: str = Field(default="rounded", description="flat, rounded, sloped")
    hairline_shape: str = Field(default="normal", description="straight, rounded, widows_peak, receding, M-shaped")
    hairline_position: str = Field(default="normal", description="low, normal, high")
    brow_bone_projection: float = Field(ge=0, le=10, description="Frontal bossing assessment")
    temple_hollowing: float = Field(ge=0, le=10, description="Temple volume (10 = full, low = hollow)")
    forehead_symmetry: float = Field(ge=0, le=10, description="Forehead symmetry")
    skin_texture: float = Field(ge=0, le=10, description="Forehead skin quality")
    notes: str = Field(default="", description="Additional observations")


class SkinMetrics(BaseModel):
    """Skin quality analysis"""
    overall_quality: float = Field(ge=0, le=10, description="Overall skin health score")
    skin_type: SkinType = Field(default=SkinType.NORMAL)
    texture_score: float = Field(ge=0, le=10, description="Skin texture smoothness")
    clarity_score: float = Field(ge=0, le=10, description="Skin clarity (blemishes, spots)")
    tone_evenness: float = Field(ge=0, le=10, description="Color evenness across face")
    hydration_appearance: float = Field(ge=0, le=10, description="Apparent hydration level")
    pore_visibility: float = Field(ge=0, le=10, description="Pore size (10 = minimal visibility)")
    acne_presence: str = Field(default="none", description="none, mild, moderate, severe")
    acne_scarring: str = Field(default="none", description="none, minimal, moderate, significant")
    hyperpigmentation: str = Field(default="none", description="none, mild, moderate, significant")
    under_eye_darkness: float = Field(ge=0, le=10, description="Dark circles severity (10 = none)")
    wrinkles_fine_lines: str = Field(default="none", description="none, minimal, moderate, significant")
    sun_damage: str = Field(default="none", description="none, mild, moderate, significant")
    notes: str = Field(default="", description="Skincare recommendations")


class FacialProportions(BaseModel):
    """Golden ratio and facial harmony measurements"""
    face_shape: FaceShape = Field(default=FaceShape.OVAL)
    facial_thirds_balance: float = Field(ge=0, le=10, description="Upper/middle/lower third balance")
    upper_third_score: float = Field(ge=0, le=10, description="Hairline to brow proportion")
    middle_third_score: float = Field(ge=0, le=10, description="Brow to nose base proportion")
    lower_third_score: float = Field(ge=0, le=10, description="Nose base to chin proportion")
    facial_width_height_ratio: Optional[float] = Field(default=None, description="FWHR measurement")
    horizontal_fifths_balance: float = Field(ge=0, le=10, description="Horizontal facial fifths")
    overall_symmetry: float = Field(ge=0, le=10, description="Complete facial symmetry")
    left_right_deviation: Optional[float] = Field(default=None, description="Percentage asymmetry")
    profile_angle: str = Field(default="straight", description="Profile: convex, straight, concave")
    facial_convexity: float = Field(ge=0, le=10, description="Profile harmony score")
    golden_ratio_adherence: float = Field(ge=0, le=10, description="Phi ratio conformity")
    notes: str = Field(default="", description="Proportion observations")


class ProfileMetrics(BaseModel):
    """Side profile analysis (from left/right photos)"""
    forehead_projection: float = Field(ge=0, le=10, description="Forehead forward projection")
    nose_projection: float = Field(ge=0, le=10, description="Nose protrusion from face")
    lip_projection: float = Field(ge=0, le=10, description="Lip projection relative to nose-chin line")
    chin_projection: float = Field(ge=0, le=10, description="Chin forward position")
    neck_angle: str = Field(default="normal", description="Neck-chin angle quality")
    submental_area: float = Field(ge=0, le=10, description="Under chin definition (10 = defined)")
    gonial_angle_left: Optional[float] = Field(default=None, description="Left jaw angle in degrees")
    gonial_angle_right: Optional[float] = Field(default=None, description="Right jaw angle in degrees")
    ramus_visibility: float = Field(ge=0, le=10, description="Jaw ramus visibility from side")
    ear_position: str = Field(default="normal", description="Ear placement relative to face")
    profile_harmony: float = Field(ge=0, le=10, description="Overall profile balance")
    notes: str = Field(default="", description="Profile observations")


class HairMetrics(BaseModel):
    """Hair analysis"""
    density: float = Field(ge=0, le=10, description="Hair density/fullness")
    hairline_health: float = Field(ge=0, le=10, description="Hairline condition")
    recession_level: str = Field(default="none", description="none, minimal, moderate, significant, severe")
    crown_thinning: str = Field(default="none", description="none, minimal, moderate, significant")
    hair_quality: float = Field(ge=0, le=10, description="Hair texture and health")
    style_suitability: str = Field(default="", description="Suggested style directions")
    notes: str = Field(default="", description="Hair care recommendations")


class BodyFatIndicators(BaseModel):
    """Facial body fat indicators"""
    facial_leanness: float = Field(ge=0, le=10, description="Overall facial leanness")
    buccal_fat_level: str = Field(default="average", description="low, average, high")
    submental_fat: str = Field(default="minimal", description="minimal, moderate, significant")
    jowl_presence: str = Field(default="none", description="none, minimal, moderate, significant")
    definition_potential: float = Field(ge=0, le=10, description="Potential with fat loss")
    estimated_body_fat_range: str = Field(default="", description="Estimated BF% range based on face")
    notes: str = Field(default="", description="Fat loss recommendations")


# ============================================
# COMPLETE FACE ANALYSIS RESULT
# ============================================

class ImprovementSuggestion(BaseModel):
    """Individual improvement recommendation"""
    area: str = Field(description="Area of focus (e.g., 'jawline', 'skin')")
    priority: ImprovementPriority = Field(default=ImprovementPriority.MEDIUM)
    current_score: float = Field(ge=0, le=10)
    potential_score: float = Field(ge=0, le=10)
    suggestion: str = Field(description="Specific actionable advice")
    exercises: List[str] = Field(default_factory=list, description="Recommended exercises")
    products: List[str] = Field(default_factory=list, description="Recommended products")
    timeframe: str = Field(default="", description="Expected timeframe for results")
    course_id: Optional[str] = Field(default=None, description="Related course ID")


class FaceMetrics(BaseModel):
    """Complete exhaustive face metrics - Structured Output for Gemini"""
    
    # Core scores
    overall_score: float = Field(ge=0, le=10, description="Composite attractiveness score")
    masculinity_score: Optional[float] = Field(default=None, ge=0, le=10, description="Masculine feature score (for male users)")
    femininity_score: Optional[float] = Field(default=None, ge=0, le=10, description="Feminine feature score (for female users)")
    harmony_score: float = Field(ge=0, le=10, description="Overall facial harmony")
    
    # Detailed metrics by area
    jawline: JawlineMetrics
    cheekbones: CheekbonesMetrics
    eye_area: EyeAreaMetrics
    nose: NoseMetrics
    lips: LipsMetrics
    forehead: ForeheadMetrics
    skin: SkinMetrics
    proportions: FacialProportions
    profile: ProfileMetrics
    hair: HairMetrics
    body_fat: BodyFatIndicators
    
    # Analysis metadata
    confidence_score: float = Field(ge=0, le=1, description="AI confidence in analysis")
    image_quality_front: float = Field(ge=0, le=10, description="Front photo quality")
    image_quality_left: float = Field(ge=0, le=10, description="Left profile quality")
    image_quality_right: float = Field(ge=0, le=10, description="Right profile quality")


class ScanAnalysis(BaseModel):
    """Complete scan analysis result (Legacy & New combined)"""
    # Legacy fields (kept for compatibility)
    metrics: Optional[FaceMetrics] = None
    improvements: Optional[List[ImprovementSuggestion]] = None
    top_strengths: Optional[List[str]] = None
    focus_areas: Optional[List[str]] = None
    recommended_courses: Optional[List[str]] = None
    personalized_summary: Optional[str] = None
    estimated_potential: Optional[float] = None
    
    # New detailed fields - matching the cannon face analysis JSON response
    success: Optional[bool] = None
    scan_summary: Optional[AdvancedScanSummary] = None
    measurements: Optional[AdvancedMeasurements] = None
    golden_ratio_analysis: Optional[GoldenRatioAnalysis] = None
    ai_recommendations: Optional[AdvancedAIRecommendations] = None
    processed_image: Optional[str] = None
    
    # Additional fields from the JSON response
    frames_analyzed: Optional[int] = None
    frames_by_angle: Optional[Dict[str, int]] = None
    overall_score: Optional[float] = None


# ============================================
# UMAX-STYLE TRIPLE PHOTO (Gemini 6 metrics)
# ============================================


class UmaxMetricRow(BaseModel):
    """One row on the pre-pay UMax-style results screen.

    Note: No Field(ge/le/default_factory) — Gemini response_schema rejects JSON-Schema
    maximum/minimum/default for some types. Clamp scores in code after parse.
    """

    id: str
    label: str
    score: float
    summary: str

    @field_validator("id", "label", "summary", mode="before")
    @classmethod
    def _coerce_umax_metric_text(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (int, float)):
            return str(v)
        return str(v).strip()


class UmaxTripleScanResult(BaseModel):
    """Structured Gemini output for front + left + right photos."""

    overall_score: float
    metrics: List[UmaxMetricRow]
    preview_blurb: str


class PslFeatureCell(BaseModel):
    """One feature row in PSL breakdown (Gemini schema: all keys required)."""

    score: float
    tag: str
    notes: str

    @field_validator("tag", "notes", mode="before")
    @classmethod
    def _coerce_feature_tag_notes(cls, v: Any) -> str:
        if v is None:
            return ""
        # Gemini sometimes emits numbers/null where we expect text.
        if isinstance(v, (int, float)):
            return str(v)
        return str(v).strip()


class PslFeatureScoresBlock(BaseModel):
    eyes: PslFeatureCell
    jaw: PslFeatureCell
    cheekbones: PslFeatureCell
    chin: PslFeatureCell
    nose: PslFeatureCell
    lips: PslFeatureCell
    brow_ridge: PslFeatureCell
    skin: PslFeatureCell
    hairline: PslFeatureCell
    symmetry: PslFeatureCell


class PslProportionsBlock(BaseModel):
    facial_thirds: str
    golden_ratio_percent: float
    bigonial_bizygomatic_ratio: float
    fwhr: float

    @field_validator("facial_thirds", mode="before")
    @classmethod
    def _coerce_facial_thirds(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (int, float)):
            return str(v)
        return str(v).strip()


class PslSideProfileBlock(BaseModel):
    maxillary_projection: str
    mandibular_projection: str
    gonial_angle: str
    submental_angle: str
    ricketts_e_line: str
    forward_head_posture: bool

    @field_validator(
        "maxillary_projection",
        "mandibular_projection",
        "gonial_angle",
        "submental_angle",
        "ricketts_e_line",
        mode="before",
    )
    @classmethod
    def _coerce_profile_text(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, bool):
            return "yes" if v else "no"
        if isinstance(v, (int, float)):
            return str(v)
        return str(v).strip()

    @field_validator("forward_head_posture", mode="before")
    @classmethod
    def _coerce_forward_head(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None or v == "":
            return False
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "y")
        return False


class TripleFullScanResult(BaseModel):
    """
    PSL-style facial rating (single Gemini vision pass) + six UMax metric rows + app tags.
    No Field(default=...) — Gemini response_schema rejects JSON-Schema defaults.
    """

    psl_score: float
    psl_tier: str
    potential: float
    archetype: str
    appeal: float
    ascension_time_months: int
    age_score: int
    weakest_link: str
    aura_tags: List[str]
    feature_scores: PslFeatureScoresBlock
    proportions: PslProportionsBlock
    side_profile: PslSideProfileBlock
    masculinity_index: float
    mog_percentile: int
    glow_up_potential: int
    metrics: List[UmaxMetricRow]
    preview_blurb: str
    problems: List[str]
    suggested_modules: List[str]

    @field_validator(
        "psl_score",
        "potential",
        "appeal",
        "masculinity_index",
        mode="before",
    )
    @classmethod
    def _coerce_float_fields(cls, v: Any) -> float:
        if v is None:
            return 0.0
        if isinstance(v, bool):
            return float(v)
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(str(v).strip())
        except Exception:
            return 0.0

    @field_validator(
        "ascension_time_months",
        "age_score",
        "mog_percentile",
        "glow_up_potential",
        mode="before",
    )
    @classmethod
    def _coerce_int_fields(cls, v: Any) -> int:
        if v is None:
            return 0
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, (int, float)):
            return int(round(float(v)))
        try:
            return int(round(float(str(v).strip())))
        except Exception:
            return 0

    @field_validator("aura_tags", "problems", "suggested_modules", mode="before")
    @classmethod
    def _coerce_list_of_strings(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            # If Gemini returns a single string instead of a list.
            item = v.strip()
            return [item] if item else []
        if isinstance(v, list):
            out: List[str] = []
            for item in v:
                if item is None:
                    continue
                if isinstance(item, (int, float)):
                    s = str(item).strip()
                else:
                    s = str(item).strip()
                if s:
                    out.append(s)
            return out
        # Unknown shape; best-effort stringification so parse can proceed.
        s = str(v).strip()
        return [s] if s else []

    @field_validator(
        "weakest_link",
        "archetype",
        "psl_tier",
        "preview_blurb",
        mode="before",
    )
    @classmethod
    def _coerce_main_text(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (int, float)):
            return str(v)
        return str(v).strip()


# ============================================
# SCAN REQUEST/RESPONSE MODELS
# ============================================

class ScanCreate(BaseModel):
    """Request to create a new scan"""
    front_image_url: str
    left_image_url: str
    right_image_url: str


class ScanResponse(BaseModel):
    """Scan response for API"""
    id: str
    user_id: str
    created_at: datetime
    images: dict
    analysis: Optional[Any] = None
    is_unlocked: bool = False
    
    class Config:
        from_attributes = True


class ScanInDB(BaseModel):
    """Full scan model as stored in database"""
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    images: dict = Field(default_factory=dict)
    analysis: Optional[Any] = None
    is_unlocked: bool = False
    processing_status: str = Field(default="pending")  # pending, processing, completed, failed
    error_message: Optional[str] = None

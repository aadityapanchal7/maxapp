"""
User Models - Pydantic schemas for user data
"""

import re
from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum


def _coerce_optional_body_metric(value: Any) -> Optional[float]:
    """Parse height/weight from float/int or strings like '180.3cm', '75 kg' (onboarding / DB legacy)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        m = re.search(r"[\d.]+", s.replace(",", "."))
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None
    return None


class ExperienceLevel(str, Enum):
    """User experience level with lookmaxxing"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class GoalType(str, Enum):
    """User improvement goals"""
    JAWLINE = "jawline"
    FAT_LOSS = "fat_loss"
    SKIN = "skin"
    POSTURE = "posture"
    SYMMETRY = "symmetry"
    HAIR = "hair"
    OVERALL = "overall"
    # Frontend goal IDs
    BONEMAX = "bonemax"
    HEIGHTMAX = "heightmax"
    SKINMAX = "skinmax"
    HAIRMAX = "hairmax"
    FITMAX = "fitmax"


class OnboardingData(BaseModel):
    """User onboarding questionnaire data (JSON on User — extra keys allowed for forward compat)."""

    model_config = ConfigDict(extra="allow")

    goals: List[GoalType] = Field(default_factory=list)
    experience_level: ExperienceLevel = ExperienceLevel.BEGINNER
    age: Optional[int] = None
    gender: Optional[str] = None
    height: Optional[float] = None  # in cm
    weight: Optional[float] = None  # in kg
    activity_level: Optional[str] = None
    skin_type: Optional[str] = None
    equipment: List[str] = Field(default_factory=list)
    unit_system: str = Field(default="imperial", description="metric or imperial")
    timezone: str = Field(default="UTC", description="IANA timezone name, e.g. America/New_York")
    # Global schedule anchors — reused when starting any maxx module if already collected
    wake_time: Optional[str] = Field(default=None, description="Usual wake time HH:MM (24h), e.g. 07:00")
    sleep_time: Optional[str] = Field(default=None, description="Usual sleep time HH:MM (24h), e.g. 23:00")
    completed: bool = False
    # Profile questionnaire v2 (collected before pay in app flow) — optional flag for clients
    questionnaire_v2_completed: Optional[bool] = None
    # Rank: face_structure, skin, hair, body, height (first = highest notification priority)
    priority_order: Optional[List[str]] = None
    appearance_concerns: Optional[List[str]] = None
    waist_cm: Optional[float] = None
    # Skin (conditional)
    primary_skin_concern: Optional[str] = None
    secondary_skin_concern: Optional[str] = None
    skincare_routine_level: Optional[str] = None
    # Hair (conditional)
    hair_family_history: Optional[str] = None
    hair_current_loss: Optional[str] = None
    hair_treatments_current: Optional[str] = None
    hair_side_effect_sensitivity: Optional[str] = None
    # Fitness / FitMax (conditional)
    fitmax_primary_goal: Optional[str] = None
    fitmax_training_experience: Optional[str] = None
    fitmax_equipment: Optional[str] = None
    fitmax_workout_days_per_week: Optional[int] = None
    preferred_workout_time: Optional[str] = Field(
        default=None, description="HH:MM 24h — pre/post workout notifications"
    )
    screen_hours_daily: Optional[str] = None
    scan_suggested_hair_focus: Optional[bool] = Field(
        default=None, description="True if latest scan metrics hinted at hair as a weak area"
    )
    post_subscription_onboarding: Optional[bool] = Field(
        default=None,
        description="When True, client should show post-pay scan insights then module select once.",
    )
    sendblue_connect_completed: Optional[bool] = Field(
        default=None,
        description="User finished in-app step to text the Max Sendblue line after subscribe.",
    )
    sendblue_sms_engaged: Optional[bool] = Field(
        default=None,
        description="True after first inbound SMS/iMessage to our Sendblue number; enables automated outbound SMS.",
    )
    facial_scan_summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Denormalized scan headline fields after first triple scan completes.",
    )

    @field_validator("height", "weight", "waist_cm", mode="before")
    @classmethod
    def parse_height_weight(cls, v: Any) -> Optional[float]:
        return _coerce_optional_body_metric(v)

    @field_validator("fitmax_workout_days_per_week", mode="before")
    @classmethod
    def coerce_fitmax_days(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        if isinstance(v, bool):
            return None
        try:
            n = int(float(str(v).strip()))
            return max(1, min(7, n))
        except (ValueError, TypeError):
            return None


class UserProfile(BaseModel):
    """User profile metrics"""
    current_level: float = Field(default=0.0, ge=0, le=10)
    rank: int = Field(default=0, ge=0)
    total_users: int = Field(default=0, ge=0)
    streak_days: int = Field(default=0, ge=0)
    improvement_percentage: float = Field(default=0.0)
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


class UserCreate(BaseModel):
    """Schema for user registration"""
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    username: str = Field(..., min_length=3, max_length=30, pattern="^[a-zA-Z0-9_]+$")
    bio: Optional[str] = None
    phone_number: str = Field(..., min_length=7, description="Phone number for SMS (with country code, e.g. +15551234567)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "securepassword123",
                "first_name": "John",
                "last_name": "Doe",
                "username": "johndoe",
                "phone_number": "+919876543210"
            }
        }


class UserLogin(BaseModel):
    """Login with email, username, or phone (JSON: `identifier` or legacy `email`)."""

    identifier: str = Field(..., validation_alias=AliasChoices("identifier", "email"))
    password: str


class ForgotPasswordSmsRequest(BaseModel):
    """Request SMS reset code — must match account phone on file."""

    phone_number: str = Field(..., min_length=7, description="E.164 or local with country code")


class ForgotPasswordSmsConfirm(BaseModel):
    """Complete reset after receiving SMS code."""

    phone_number: str = Field(..., min_length=7)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8, max_length=100)


class AuthMessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    """Schema for user response (public data)"""
    id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    last_username_change: Optional[datetime] = None
    created_at: datetime
    is_paid: bool = False
    subscription_status: Optional[str] = None
    subscription_end_date: Optional[datetime] = None
    onboarding: OnboardingData = Field(default_factory=OnboardingData)
    profile: UserProfile = Field(default_factory=UserProfile)
    first_scan_completed: bool = False
    is_admin: bool = False
    phone_number: Optional[str] = None
    
    class Config:
        from_attributes = True


class UserInDB(BaseModel):
    """Full user model as stored in database"""
    email: EmailStr
    password_hash: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_paid: bool = False
    is_admin: bool = False
    subscription_status: Optional[str] = None  # active, canceled, past_due
    subscription_id: Optional[str] = None
    subscription_end_date: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    onboarding: OnboardingData = Field(default_factory=OnboardingData)
    profile: UserProfile = Field(default_factory=UserProfile)
    first_scan_completed: bool = False
    phone_number: Optional[str] = None


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT token payload"""
    sub: str  # user_id
    exp: datetime
    type: str  # access or refresh
class TokenRefreshRequest(BaseModel):
    """Request to refresh access token"""
    refresh_token: str


class AccountUpdateRequest(BaseModel):
    """Request to update user account info"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None


class BlockUserRequest(BaseModel):
    """Block another user from appearing in community channels for the current user."""

    blocked_user_id: str = Field(..., min_length=1, max_length=64)


class DeleteAccountRequest(BaseModel):
    """Confirm account deletion with password (App Store Guideline 5.1.1)."""

    password: str = Field(..., min_length=1, max_length=200)

"""
User Models - Pydantic schemas for user data
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


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
    """User onboarding questionnaire data"""
    goals: List[GoalType] = Field(default_factory=list)
    experience_level: ExperienceLevel = ExperienceLevel.BEGINNER
    age: Optional[int] = None
    gender: Optional[str] = None
    height: Optional[float] = None  # in cm
    weight: Optional[float] = None  # in kg
    activity_level: Optional[str] = None
    skin_type: Optional[str] = None
    equipment: List[str] = Field(default_factory=list)
    unit_system: str = Field(default="metric", description="metric or imperial")
    timezone: str = Field(default="UTC", description="IANA timezone name, e.g. America/New_York")
    completed: bool = False


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
    phone_number: Optional[str] = Field(default=None, description="Phone number with country code, e.g. +919876543210")
    
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
    """Schema for user login"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user response (public data)"""
    id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
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

"""
Course Models - Structured improvement courses
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from models.schedule import ModuleGuideline


class CourseCategory(str, Enum):
    """Course category types"""
    # Legacy / generic categories
    JAWLINE = "jawline"
    SKIN = "skin"
    FAT_LOSS = "fat_loss"
    POSTURE = "posture"
    MEWING = "mewing"
    SKINCARE = "skincare"
    HAIR = "hair"
    MINDSET = "mindset"

    # App-specific maxx tracks
    BONEMAX = "bonemax"
    HEIGHTMAX = "heightmax"
    SKINMAX = "skinmax"
    HAIRMAX = "hairmax"
    FITMAX = "fitmax"


class ChapterType(str, Enum):
    """Content type for a chapter"""
    TEXT = "text"
    VIDEO = "video"
    IMAGE = "image"
    QUIZ = "quiz"


class CourseChapter(BaseModel):
    """Individual chapter within a course module"""
    chapter_id: str
    title: str
    description: str
    type: ChapterType = Field(default=ChapterType.TEXT)
    content: Optional[str] = Field(default=None, description="Text content or markdown")
    video_url: Optional[str] = Field(default=None, description="URL for video content")
    image_url: Optional[str] = Field(default=None, description="URL for image content")
    duration_minutes: int = Field(default=10, ge=1)
    
    # Legacy support (optional)
    instructions: List[str] = Field(default_factory=list)
    tips: List[str] = Field(default_factory=list)


class CourseModule(BaseModel):
    """Module within a course (formerly Stage)"""
    module_number: int = Field(ge=1)
    title: str
    description: str
    chapters: List[CourseChapter] = Field(default_factory=list)
    unlock_after_days: int = Field(default=0, description="Days from start to unlock")
    guidelines: Optional[ModuleGuideline] = Field(default=None, description="Loose AI guidelines for schedule generation")


class CourseCreate(BaseModel):
    """Request to create a new course (admin)"""
    title: str
    description: str
    category: CourseCategory
    thumbnail_url: Optional[str] = None
    difficulty: str = Field(default="beginner")
    estimated_weeks: int = Field(default=4, ge=1)
    modules: List[CourseModule] = Field(default_factory=list)


class CourseResponse(BaseModel):
    """Course response for API"""
    id: str
    title: str
    description: str
    category: CourseCategory
    thumbnail_url: Optional[str] = None
    difficulty: str
    estimated_weeks: int
    modules: List[CourseModule] = Field(default_factory=list)
    total_chapters: int = 0
    is_active: bool = True
    created_at: datetime
    
    class Config:
        from_attributes = True


class CourseInDB(BaseModel):
    """Full course model as stored in database"""
    title: str
    description: str
    category: CourseCategory
    thumbnail_url: Optional[str] = None
    difficulty: str = "beginner"
    estimated_weeks: int = 4
    modules: List[CourseModule] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CourseProgress(BaseModel):
    """User's progress in a course"""
    id: str
    user_id: str
    course_id: str
    course_title: str
    current_module: int = 1
    completed_chapters: List[str] = Field(default_factory=list)
    progress_percentage: float = Field(default=0.0, ge=0, le=100)
    started_at: datetime
    last_activity: datetime
    is_completed: bool = False
    
    class Config:
        from_attributes = True


class CourseProgressInDB(BaseModel):
    """Full progress model as stored in database"""
    user_id: str
    course_id: str
    current_module: int = 1
    completed_chapters: List[str] = Field(default_factory=list)
    progress_percentage: float = 0.0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    is_completed: bool = False


class ChapterCompletionRequest(BaseModel):
    """Request to mark a chapter as complete"""
    chapter_id: str
    module_number: int

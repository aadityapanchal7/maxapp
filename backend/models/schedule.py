"""
Schedule Models - AI-powered personalized schedules for course modules
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, time
from enum import Enum


class TaskType(str, Enum):
    """Types of scheduled activities"""
    EXERCISE = "exercise"
    ROUTINE = "routine"
    REMINDER = "reminder"
    CHECKPOINT = "checkpoint"


class TaskStatus(str, Enum):
    """Status of a scheduled task"""
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class ModuleGuideline(BaseModel):
    """Loose AI guidelines for a course module — fed to Gemini for schedule generation"""
    exercises: List[str] = Field(default_factory=list, description="List of exercise names/types")
    frequency_hints: List[str] = Field(default_factory=list, description="e.g. '2x daily', 'every morning'")
    duration_ranges: List[str] = Field(default_factory=list, description="e.g. '20-30 min', '2-4 hours'")
    tips: List[str] = Field(default_factory=list, description="General coaching tips for the AI")
    difficulty_progression: str = Field(default="gradual", description="How to ramp intensity: gradual, aggressive, steady")
    focus_areas: List[str] = Field(default_factory=list, description="Body/face areas this module targets")
    recommended_days: int = Field(default=7, ge=1, le=90, description="Recommended schedule length for this module")


class ScheduleTask(BaseModel):
    """A single scheduled activity"""
    task_id: str
    time: str = Field(description="Time string e.g. '07:00', '12:30'")
    title: str
    description: str
    task_type: TaskType = TaskType.EXERCISE
    duration_minutes: int = Field(default=15, ge=1)
    status: TaskStatus = TaskStatus.PENDING
    completed_at: Optional[datetime] = None
    notification_sent: bool = False


class DailySchedule(BaseModel):
    """One day's schedule"""
    day_number: int = Field(ge=1, description="Day number in the program (1-indexed)")
    date: Optional[str] = Field(default=None, description="ISO date string e.g. '2026-03-08'")
    tasks: List[ScheduleTask] = Field(default_factory=list)
    motivation_message: str = Field(default="", description="AI-generated daily motivation")


class SchedulePreferences(BaseModel):
    """User preferences for schedule generation"""
    wake_time: str = Field(default="07:00", description="Preferred wake time (HH:MM)")
    sleep_time: str = Field(default="23:00", description="Preferred sleep time (HH:MM)")
    preferred_workout_times: List[str] = Field(
        default_factory=lambda: ["08:00", "18:00"],
        description="Preferred times for exercises"
    )
    notifications_enabled: bool = Field(default=True)
    notification_minutes_before: int = Field(default=5, description="Minutes before task to send reminder")


# --- API Request / Response Models ---

class GenerateScheduleRequest(BaseModel):
    """Request to generate a new course schedule"""
    course_id: str
    module_number: int = Field(ge=1)
    preferences: Optional[SchedulePreferences] = None
    num_days: int = Field(default=7, ge=1, le=90, description="Number of days to generate (overrides module default if set)")


class GenerateMaxxScheduleRequest(BaseModel):
    """Request to generate a maxx-based schedule (e.g. SkinMax)"""
    maxx_id: str = Field(description="e.g. 'skinmax', 'hairmax'")
    wake_time: str = Field(default="07:00", description="HH:MM")
    sleep_time: str = Field(default="23:00", description="HH:MM")
    skin_concern: Optional[str] = Field(default=None, description="Explicit concern override: acne, pigmentation, texture, redness, aging")
    outside_today: bool = Field(default=False, description="Whether user plans to be outside today")
    num_days: int = Field(default=7, ge=1, le=30)
    # HeightMax: optional map of protocol keys -> include in schedule (from app toggles). Omit = all on.
    height_components: Optional[dict[str, bool]] = Field(
        default=None,
        description="For heightmax only: e.g. posturemaxxing, sprintmaxxing, deep_sleep_routine — false excludes that track",
    )


class ScheduleResponse(BaseModel):
    """Schedule returned to client"""
    id: str
    user_id: str
    course_id: str
    course_title: str
    module_number: int
    days: List[DailySchedule] = Field(default_factory=list)
    preferences: SchedulePreferences = Field(default_factory=SchedulePreferences)
    is_active: bool = True
    created_at: datetime
    adapted_count: int = Field(default=0, description="How many times the AI has adapted this schedule")

    class Config:
        from_attributes = True


class ScheduleInDB(BaseModel):
    """Full schedule model as stored in database"""
    user_id: str
    course_id: str
    course_title: str
    module_number: int
    days: List[dict] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    adapted_count: int = 0
    # AI learning context
    user_feedback: List[dict] = Field(default_factory=list, description="History of user feedback for adaptation")
    completion_stats: dict = Field(default_factory=dict, description="Aggregated stats on task completion")


class CompleteTaskRequest(BaseModel):
    """Request to mark a task as complete"""
    feedback: Optional[str] = Field(default=None, description="Optional user feedback: 'too easy', 'too hard', etc.")


class AdaptScheduleRequest(BaseModel):
    """Request to adapt the schedule"""
    feedback: str = Field(description="User feedback for adaptation, e.g. 'too intense', 'need more morning tasks'")


class EditTaskRequest(BaseModel):
    """Request to edit a scheduled task"""
    time: Optional[str] = Field(default=None, description="New time e.g. '08:30'")
    title: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    duration_minutes: Optional[int] = Field(default=None, ge=1)

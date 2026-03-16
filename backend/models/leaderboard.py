"""
Leaderboard Models
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class LeaderboardEntry(BaseModel):
    """Single leaderboard entry"""
    rank: int
    user_id: str
    user_email: Optional[str] = None
    score: float
    streak_days: int
    scan_count: int
    level: float
    improvement_percentage: float


class LeaderboardResponse(BaseModel):
    """Leaderboard API response"""
    entries: list[LeaderboardEntry] = Field(default_factory=list)
    total_users: int = 0
    user_rank: Optional[LeaderboardEntry] = None


class LeaderboardInDB(BaseModel):
    """Full leaderboard entry as stored in database"""
    user_id: str
    score: float = 0.0
    streak_days: int = 0
    scan_count: int = 0
    course_completion_rate: float = 0.0
    activity_score: float = 0.0
    forum_posts: int = 0
    rank: int = 0
    level: float = 0.0
    improvement_percentage: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    """Chat message for Max Chat"""
    role: str = Field(description="user or assistant")
    content: str
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    """Request to send chat message"""
    message: str
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None
    init_context: Optional[str] = Field(default=None, description="Optional context for schedule init, e.g. 'skinmax'")


class ChatResponse(BaseModel):
    """Chat response"""
    response: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatHistoryInDB(BaseModel):
    """Chat history stored in database"""
    user_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

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
    chat_intent: Optional[str] = Field(
        default=None,
        description="Optional explicit client intent, e.g. 'start_schedule'",
    )
    # Multi-conversation: when omitted, the server reuses the user's most-recent
    # conversation (or creates one on first message) so legacy single-thread
    # clients keep working.
    conversation_id: Optional[str] = Field(
        default=None,
        description="Target chat_conversations.id. Omit to auto-route to latest / new thread.",
    )
    # iMessage-style "reply to a specific earlier message". Mobile sets this
    # when the user swipes right on a bubble and types a reply. The backend
    # fetches the referenced message + prepends it to the LLM context as
    # "user is replying to this earlier turn:" so the response treats the
    # quoted turn as the focal subject. Persisted on the new chat_history
    # row so the transcript renders the quoted strip on reload.
    reply_to_message_id: Optional[str] = Field(
        default=None,
        description="chat_history.id the user is replying to (iMessage-style swipe-reply).",
    )


class ChatResponse(BaseModel):
    """Chat response"""
    response: str
    choices: list[str] = Field(default_factory=list)
    # Optional structured input widget the mobile client renders inline below
    # the assistant bubble. Currently used for numeric questions:
    #   {"type":"slider","min":13,"max":50,"step":1,"default":18,"label":"How old are you?"}
    # Mobile client interprets `type` and renders a slider + Submit button that
    # sends the chosen value back as the next user message.
    input_widget: Optional[dict] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Echo back the conversation the message landed in — lets the mobile client
    # discover the server-assigned id on first message without a separate call.
    conversation_id: Optional[str] = None


class ChatHistoryInDB(BaseModel):
    """Chat history stored in database"""
    user_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

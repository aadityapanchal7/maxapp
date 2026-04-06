"""
Forum v2 models - classic threads (categories -> subforums -> threads -> posts)
"""

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field


AccessTier = Literal["public", "premium"]
NotificationType = Literal["reply", "mention", "quote", "watch"]
ThreadSort = Literal["new", "hot", "top"]
PostSort = Literal["new", "top"]


class ForumCategoryResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    order: int = 0
    created_at: datetime


class ForumSubforumResponse(BaseModel):
    id: str
    category_id: str
    name: str
    slug: str
    description: Optional[str] = None
    order: int = 0
    access_tier: AccessTier = "public"
    is_read_only: bool = False
    thread_count: int = 0
    last_activity: Optional[datetime] = None


class ForumThreadCreate(BaseModel):
    subforum_id: str
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    tags: List[str] = Field(default_factory=list, max_length=12)
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None


class ForumSubforumCreate(BaseModel):
    category_id: str
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=240)


class ForumThreadResponse(BaseModel):
    id: str
    subforum_id: str
    title: str
    tags: List[str] = Field(default_factory=list)
    is_sticky: bool = False
    is_locked: bool = False
    view_count: int = 0
    reply_count: int = 0
    last_post_at: Optional[datetime] = None
    created_at: datetime
    created_by: Optional[str] = None
    created_by_username: Optional[str] = None


class ForumPostCreate(BaseModel):
    content: str = Field(default="", max_length=8000)
    parent_post_id: Optional[str] = None
    quote_post_id: Optional[str] = None
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None


class ForumPostResponse(BaseModel):
    id: str
    thread_id: str
    user_id: str
    username: Optional[str] = None
    user_avatar_url: Optional[str] = None
    content: str
    entities: dict = Field(default_factory=dict)
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None
    parent_post_id: Optional[str] = None
    score: int = 0
    upvotes: int = 0
    downvotes: int = 0
    created_at: datetime


class ForumVoteRequest(BaseModel):
    value: int = Field(description="+1 or -1")


class ForumWatchRequest(BaseModel):
    watch: bool = True


class ForumNotificationResponse(BaseModel):
    id: str
    type: NotificationType
    entity_id: str
    actor_user_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    is_read: bool = False
    created_at: datetime


class ForumReportCreate(BaseModel):
    reason: str = Field(default="", max_length=2000)


# --- Admin (full CRUD; any category / access tier) ---


class AdminForumCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    order: int = 0


class AdminForumCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=2000)
    order: Optional[int] = None


class AdminForumSubforumCreate(BaseModel):
    category_id: str
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=240)
    access_tier: AccessTier = "public"
    is_read_only: bool = False
    order: Optional[int] = None


class AdminForumSubforumUpdate(BaseModel):
    category_id: Optional[str] = None
    name: Optional[str] = Field(None, min_length=2, max_length=60)
    description: Optional[str] = Field(None, max_length=240)
    access_tier: Optional[AccessTier] = None
    is_read_only: Optional[bool] = None
    order: Optional[int] = None


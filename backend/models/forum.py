"""
Channel Models - Discord-like chat channels
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ChannelCreate(BaseModel):
    """Request to create a new channel"""
    name: str
    slug: Optional[str] = Field(default=None, description="URL-friendly identifier")
    description: str
    is_admin_only: bool = Field(default=False, description="If true, only admins can post")
    icon: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    order: int = Field(default=0, description="Display order")


class ChannelResponse(BaseModel):
    """Channel response"""
    id: str
    name: str
    slug: str
    description: str
    is_admin_only: bool
    icon: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    message_count: int = 0
    last_activity: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChannelInDB(BaseModel):
    """Full channel model as stored in database"""
    name: str
    slug: str
    description: str
    is_admin_only: bool = False
    icon: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    order: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MessageCreate(BaseModel):
    """Request to send a message in a channel"""
    content: str
    parent_id: Optional[str] = None
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None


class MessageResponse(BaseModel):
    """Message response for API"""
    id: str
    channel_id: str
    user_id: str
    user_email: str
    content: str
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None
    created_at: datetime
    is_admin: bool = False
    parent_id: Optional[str] = None
    reactions: dict = Field(default_factory=dict)
    
    class Config:
        from_attributes = True


class MessageInDB(BaseModel):
    """Full message model as stored in database"""
    channel_id: str
    user_id: str
    content: str
    attachment_url: Optional[str] = None
    attachment_type: Optional[str] = None
    parent_id: Optional[str] = None
    reactions: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# Legacy aliases for backwards compatibility during migration
ForumCreate = ChannelCreate
ForumResponse = ChannelResponse
ForumInDB = ChannelInDB

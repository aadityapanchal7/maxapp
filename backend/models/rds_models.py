"""
SQLAlchemy ORM Models for AWS RDS PostgreSQL
Shared/multi-user data (courses, forums/channels, events)
"""

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Text,
    Integer,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


class Maxx(Base):
    """Looksmaxxing programs (fitmax, skinmax, etc.)"""
    __tablename__ = "maxes"

    id = Column(String, primary_key=True)  # e.g. "fitmax"
    label = Column(String, nullable=False)  # e.g. "Fitmax"
    description = Column(Text)
    icon = Column(String)
    color = Column(String)
    modules = Column(JSON, default=list)   # [{title, description, steps:[{title,content}]}]
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Schedule guidelines (for maxxes with AI-generated schedules)
    # protocols: { concern_id: { label, am, pm, weekly, sunscreen, ... } } - structure varies by maxx
    protocols = Column(JSON, default=dict)
    # schedule_rules: { am_timing, pm_timing, sunscreen_reapply, ... }
    schedule_rules = Column(JSON, default=dict)
    # concern_mapping: { skin_type: concern_id } - optional fallback when user hasn't picked
    concern_mapping = Column(JSON, default=dict)
    # concern_question: "What's your ONE main skin concern? Pick one: Acne, Pigmentation, ..."
    concern_question = Column(Text)
    # concerns: [{ id, label }] - options to show when asking user
    concerns = Column(JSON, default=list)
    # protocol_prompt_template: template for building prompt section, uses {label}, {am}, {pm}, etc.
    protocol_prompt_template = Column(Text)

    __table_args__ = (
        Index("idx_maxes_active", is_active),
    )


class Course(Base):
    """Structured improvement courses"""
    __tablename__ = "courses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text)
    category = Column(String)
    thumbnail_url = Column(Text)
    difficulty = Column(String, default="beginner")
    estimated_weeks = Column(Integer, default=4)
    modules = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_courses_category", category),
        Index("idx_courses_active", is_active),
    )


class Forum(Base):
    """Community channels (forums)"""
    __tablename__ = "forums"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    slug = Column(String, nullable=False, unique=True)
    description = Column(Text)
    icon = Column(Text)
    category = Column(String)
    tags = Column(JSON, default=list)
    order = Column(Integer, default=0)
    is_admin_only = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_forums_order", order),
        Index("idx_forums_admin_only", is_admin_only),
    )


class ChannelMessage(Base):
    """Messages posted inside channels"""
    __tablename__ = "channel_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("forums.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)  # References Supabase users

    content = Column(Text, nullable=False)
    attachment_url = Column(Text)
    attachment_type = Column(String)
    parent_id = Column(UUID(as_uuid=True))
    reactions = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_channel_messages_channel_id", channel_id),
        Index("idx_channel_messages_user_id", user_id),
        Index("idx_channel_messages_created_at", created_at),
    )


class Event(Base):
    """Live events"""
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer)
    tiktok_link = Column(Text)
    thumbnail_url = Column(Text)
    is_live = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_events_scheduled_at", scheduled_at),
        Index("idx_events_is_live", is_live),
    )

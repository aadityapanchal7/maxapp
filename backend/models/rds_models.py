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
    created_by = Column(UUID(as_uuid=True))
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


# ---------------------------------------------------------------------------
# Forum v2 (classic threads)
# ---------------------------------------------------------------------------


class ForumCategory(Base):
    __tablename__ = "forum_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    slug = Column(String, nullable=False, unique=True)
    description = Column(Text)
    order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_categories_order", order),
    )


class ForumSubforum(Base):
    __tablename__ = "forum_subforums"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = Column(UUID(as_uuid=True), ForeignKey("forum_categories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    description = Column(Text)
    order = Column(Integer, default=0)
    access_tier = Column(String, default="public")  # public | premium
    is_read_only = Column(Boolean, default=False)
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_subforums_category_id", category_id),
        Index("idx_forum_subforums_order", order),
        Index("idx_forum_subforums_access_tier", access_tier),
    )


class ForumThread(Base):
    __tablename__ = "forum_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subforum_id = Column(UUID(as_uuid=True), ForeignKey("forum_subforums.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String, nullable=False)
    tags = Column(JSON, default=list)
    is_sticky = Column(Boolean, default=False)
    is_locked = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    last_post_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_post_user_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_threads_subforum_id", subforum_id),
        Index("idx_forum_threads_last_post_at", last_post_at),
        Index("idx_forum_threads_user_id", user_id),
        Index("idx_forum_threads_sticky", is_sticky),
    )


class ForumPost(Base):
    __tablename__ = "forum_posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("forum_threads.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    content = Column(Text, nullable=False)
    entities = Column(JSON, default=dict)  # mentions, quote refs, etc.
    attachment_url = Column(Text)
    attachment_type = Column(String)
    parent_post_id = Column(UUID(as_uuid=True))
    score = Column(Integer, default=0)
    upvotes = Column(Integer, default=0)
    downvotes = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_posts_thread_id", thread_id),
        Index("idx_forum_posts_user_id", user_id),
        Index("idx_forum_posts_created_at", created_at),
        Index("idx_forum_posts_score", score),
    )


class ForumPostVote(Base):
    __tablename__ = "forum_post_votes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = Column(UUID(as_uuid=True), ForeignKey("forum_posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    value = Column(Integer, nullable=False)  # +1 or -1
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_post_votes_post_id", post_id),
        Index("idx_forum_post_votes_user_id", user_id),
        Index("uq_forum_post_votes_post_user", post_id, user_id, unique=True),
    )


class ForumThreadWatch(Base):
    __tablename__ = "forum_thread_watches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("forum_threads.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_thread_watches_thread_id", thread_id),
        Index("idx_forum_thread_watches_user_id", user_id),
        Index("uq_forum_thread_watches_thread_user", thread_id, user_id, unique=True),
    )


class ForumNotification(Base):
    __tablename__ = "forum_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    type = Column(String, nullable=False)  # reply | mention | quote | watch
    entity_id = Column(UUID(as_uuid=True), nullable=False)  # thread_id or post_id
    actor_user_id = Column(UUID(as_uuid=True))
    payload = Column(JSON, default=dict)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_notifications_user_id", user_id),
        Index("idx_forum_notifications_created_at", created_at),
        Index("idx_forum_notifications_is_read", is_read),
    )


class ForumPostReport(Base):
    __tablename__ = "forum_post_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = Column(UUID(as_uuid=True), ForeignKey("forum_posts.id", ondelete="CASCADE"), nullable=False)
    reporter_user_id = Column(UUID(as_uuid=True), nullable=False)
    reason = Column(Text)
    status = Column(String, default="open")  # open | resolved | dismissed
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_post_reports_post_id", post_id),
        Index("idx_forum_post_reports_reporter_user_id", reporter_user_id),
        Index("idx_forum_post_reports_status", status),
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

"""
SQLAlchemy ORM Models for AWS RDS PostgreSQL
Shared/multi-user data (courses, forums, events)
"""

from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Text, Integer, ForeignKey, Index, Table, UniqueConstraint, CheckConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


# ========== SHARED DATA (AWS RDS) ==========

class Course(Base):
    """Training courses"""
    __tablename__ = "courses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text)
    instructor_id = Column(String)  # Reference to instructor/admin
    level = Column(String, CheckConstraint("level IN ('beginner', 'intermediate', 'advanced')"))
    duration_minutes = Column(Integer)
    price = Column(Numeric(10, 2))
    is_published = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_courses_level", level),
        Index("idx_courses_published", is_published),
    )


class Lesson(Base):
    """Individual lessons within courses"""
    __tablename__ = "lessons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    content = Column(Text)
    video_url = Column(String)
    order = Column(Integer)
    duration_minutes = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_lessons_course_id", course_id),
        Index("idx_lessons_order", order),
    )


class Forum(Base):
    """Discussion forums"""
    __tablename__ = "forums"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text)
    category = Column(String)  # fitness, nutrition, mindset, etc
    moderator_ids = Column(JSON, default=[])  # Array of user IDs

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_forums_category", category),
    )


class ForumThread(Base):
    """Threads within forums"""
    __tablename__ = "forum_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    forum_id = Column(UUID(as_uuid=True), ForeignKey("forums.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)  # Reference to app_users
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    views = Column(Integer, default=0)
    is_pinned = Column(Boolean, default=False)
    is_locked = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_threads_forum_id", forum_id),
        Index("idx_forum_threads_user_id", user_id),
        Index("idx_forum_threads_pinned", is_pinned),
    )


class ForumReply(Base):
    """Replies to forum threads"""
    __tablename__ = "forum_replies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("forum_threads.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    content = Column(Text, nullable=False)
    likes = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_forum_replies_thread_id", thread_id),
        Index("idx_forum_replies_user_id", user_id),
    )


class Event(Base):
    """Community events and challenges"""
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text)
    type = Column(String, CheckConstraint("type IN ('challenge', 'webinar', 'meetup', 'competition')"))
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True))
    capacity = Column(Integer)
    location = Column(String)  # Virtual/physical address
    organizer_id = Column(String)  # Reference to admin/organizer
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_events_type", type),
        Index("idx_events_start_date", start_date),
        Index("idx_events_active", is_active),
    )


class EventRegistration(Base):
    """User registrations for events"""
    __tablename__ = "event_registrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)  # Reference to app_users
    status = Column(String, CheckConstraint("status IN ('registered', 'attended', 'cancelled')"), default='registered')

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_event_registrations_event_id", event_id),
        Index("idx_event_registrations_user_id", user_id),
        UniqueConstraint("event_id", "user_id", name="unique_event_user"),
    )


class Announcement(Base):
    """Site-wide announcements"""
    __tablename__ = "announcements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    author_id = Column(String)  # Reference to admin
    priority = Column(String, CheckConstraint("priority IN ('low', 'medium', 'high')"), default='medium')
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_announcements_published", is_published),
        Index("idx_announcements_priority", priority),
    )

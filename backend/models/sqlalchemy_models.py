"""
SQLAlchemy ORM Models for Supabase PostgreSQL
"""

from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Text, Integer, ForeignKey, Index, UniqueConstraint, CheckConstraint, ARRAY, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


# ========== USER-SPECIFIC DATA (Supabase) ==========

class User(Base):
    """User account and profile"""
    __tablename__ = "app_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    is_paid = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    subscription_status = Column(String, CheckConstraint("subscription_status IN ('active', 'canceled', 'past_due', NULL)"))
    subscription_id = Column(String, unique=True)
    subscription_end_date = Column(DateTime(timezone=True))
    stripe_customer_id = Column(String, unique=True)

    phone_number = Column(String)
    first_scan_completed = Column(Boolean, default=False)

    onboarding = Column(JSON, default={"goals": [], "experience_level": None, "completed": False})
    profile = Column(JSON, default={"current_level": 0, "rank": None, "streak_days": 0, "improvement_percentage": 0, "bio": None, "avatar_url": None})

    __table_args__ = (
        Index("idx_app_users_email", email),
        Index("idx_app_users_is_paid", is_paid),
        Index("idx_app_users_created_at", created_at),
    )


class Scan(Base):
    """Face scan analysis results"""
    __tablename__ = "scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    images = Column(JSON, default={"front": None, "left": None, "right": None})
    analysis = Column(JSON, default={"metrics": {}, "improvements": [], "top_strengths": [], "focus_areas": [], "recommended_courses": []})

    is_unlocked = Column(Boolean, default=False)
    processing_status = Column(String, CheckConstraint("processing_status IN ('pending', 'processing', 'completed', 'failed')"), default='pending')

    __table_args__ = (
        Index("idx_scans_user_id", user_id),
        Index("idx_scans_created_at", created_at.desc()),
        Index("idx_scans_user_created", user_id, created_at.desc()),
    )


class Payment(Base):
    """Stripe payment transactions"""
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    stripe_customer_id = Column(String)
    stripe_session_id = Column(String, unique=True)
    stripe_subscription_id = Column(String)

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default='usd')
    status = Column(String, CheckConstraint("status IN ('pending', 'completed', 'failed', 'refunded')"), default='pending')

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    subscription_status = Column(String)
    current_period_start = Column(DateTime(timezone=True))
    current_period_end = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_payments_user_id", user_id),
        Index("idx_payments_stripe_session", stripe_session_id),
        Index("idx_payments_created_at", created_at),
    )


class UserCourseProgress(Base):
    """User course enrollment and progress"""
    __tablename__ = "user_course_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(UUID(as_uuid=True), nullable=False)  # References AWS RDS

    enrollment_date = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_chapters = Column(ARRAY(String), default=[])
    current_module = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    completion_date = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="user_course_unique"),
        Index("idx_user_course_user_id", user_id),
        Index("idx_user_course_course_id", course_id),
    )


class Leaderboard(Base):
    """User leaderboard rankings"""
    __tablename__ = "leaderboard"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    score = Column(Numeric(5, 2), default=0)
    level = Column(Numeric(5, 2))
    rank = Column(Integer)
    streak_days = Column(Integer, default=0)
    scans_count = Column(Integer, default=0)
    improvement_percentage = Column(Numeric(5, 2), default=0)

    last_scan_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_leaderboard_score", score.desc()),
        Index("idx_leaderboard_rank", rank),
    )


class ChatHistory(Base):
    """AI chat conversation history"""
    __tablename__ = "chat_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    role = Column(String, CheckConstraint("role IN ('user', 'assistant')"), nullable=False)
    content = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_chat_user_id", user_id),
        Index("idx_chat_created_at", created_at.desc()),
    )


class ChannelMessage(Base):
    """Forum/community channel messages"""
    __tablename__ = "channel_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), nullable=False)  # References AWS RDS
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_channel_messages_channel_id", channel_id),
        Index("idx_channel_messages_user_id", user_id),
        Index("idx_channel_messages_channel_created", channel_id, created_at.desc()),
    )

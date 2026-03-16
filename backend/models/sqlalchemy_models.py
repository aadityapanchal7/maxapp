"""
SQLAlchemy ORM Models for Supabase PostgreSQL (user-specific data)
"""

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Numeric,
    Text,
    Integer,
    ForeignKey,
    Index,
    UniqueConstraint,
    JSON,
    Float,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, date
import uuid

Base = declarative_base()


class User(Base):
    """User account and profile"""
    __tablename__ = "app_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    first_name = Column(String)
    last_name = Column(String)
    username = Column(String, unique=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    is_paid = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    subscription_status = Column(String)
    subscription_id = Column(String, unique=True)
    subscription_end_date = Column(DateTime(timezone=True))
    stripe_customer_id = Column(String, unique=True)

    phone_number = Column(String)
    first_scan_completed = Column(Boolean, default=False)

    onboarding = Column(JSON, default=dict)
    profile = Column(JSON, default=dict)
    schedule_preferences = Column(JSON, default=dict)
    last_progress_prompt_date = Column(String)

    __table_args__ = (
        Index("idx_app_users_email", email),
        Index("idx_app_users_username", username),
        Index("idx_app_users_is_paid", is_paid),
    )


class Scan(Base):
    """Face scan analysis results"""
    __tablename__ = "scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    images = Column(JSON, default=dict)
    analysis = Column(JSON, default=dict)

    is_unlocked = Column(Boolean, default=False)
    processing_status = Column(String, default="pending")
    scan_type = Column(String, default="image")
    error_message = Column(Text)

    __table_args__ = (
        Index("idx_scans_user_id", user_id),
        Index("idx_scans_created_at", created_at.desc()),
    )


class Payment(Base):
    """Stripe payment transactions"""
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)

    stripe_customer_id = Column(String)
    stripe_session_id = Column(String, unique=True)
    stripe_subscription_id = Column(String)
    stripe_payment_intent = Column(String)

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="usd")
    status = Column(String, default="pending")

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
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(UUID(as_uuid=True), nullable=False)  # References AWS RDS
    course_title = Column(String)

    current_module = Column(Integer, default=1)
    completed_chapters = Column(JSON, default=list)
    progress_percentage = Column(Float, default=0.0)

    started_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_activity = Column(DateTime(timezone=True), default=datetime.utcnow)
    is_completed = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="user_course_unique"),
        Index("idx_user_course_user_id", user_id),
        Index("idx_user_course_course_id", course_id),
    )


class Leaderboard(Base):
    """User leaderboard rankings"""
    __tablename__ = "leaderboard"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, unique=True)

    score = Column(Numeric(8, 2), default=0)
    level = Column(Numeric(5, 2))
    rank = Column(Integer)
    streak_days = Column(Integer, default=0)
    scans_count = Column(Integer, default=0)
    improvement_percentage = Column(Numeric(6, 2), default=0)

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
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)

    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_chat_user_id", user_id),
        Index("idx_chat_created_at", created_at.desc()),
    )


class UserProgressPhoto(Base):
    """Daily progress photos for users"""
    __tablename__ = "user_progress_photos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_progress_photos_user_id", user_id),
        Index("idx_progress_photos_created_at", created_at.desc()),
    )


class UserSchedule(Base):
    """AI-generated schedules for users (course-based or maxx-based)"""
    __tablename__ = "user_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)

    schedule_type = Column(String, default="course")  # "course" or "maxx"
    course_id = Column(UUID(as_uuid=True), nullable=True)
    course_title = Column(String)
    module_number = Column(Integer, nullable=True)
    maxx_id = Column(String, nullable=True)  # e.g. "skinmax", "hairmax"

    days = Column(JSON, default=list)
    preferences = Column(JSON, default=dict)
    schedule_context = Column(JSON, default=dict)  # learned patterns, outside today, etc.
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    adapted_count = Column(Integer, default=0)
    user_feedback = Column(JSON, default=list)
    completion_stats = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_user_schedules_user_id", user_id),
        Index("idx_user_schedules_course_id", course_id),
        Index("idx_user_schedules_active", is_active),
        Index("idx_user_schedules_maxx_id", maxx_id),
    )

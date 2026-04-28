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
from sqlalchemy.dialects.postgresql import UUID, ARRAY, BIGINT, JSONB
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

# pgvector is optional -- the rag_documents table is created manually in
# Supabase (see db/sqlalchemy.py::init_db skip_tables) and DB-backed RAG no
# longer requires a Vector column at the ORM layer. Fall back to TEXT when
# the package isn't installed so `import sqlalchemy_models` never crashes
# the process on boot.
try:
    from pgvector.sqlalchemy import Vector  # type: ignore
    _PGVECTOR_AVAILABLE = True
except Exception:  # ImportError, or any transitive failure
    Vector = None  # type: ignore[assignment,misc]
    _PGVECTOR_AVAILABLE = False

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
    last_username_change = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    is_paid = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    is_scan_user = Column(Boolean, default=False)
    subscription_tier = Column(String, default=None)  # null (free), 'basic', 'premium'
    subscription_status = Column(String)
    subscription_id = Column(String)
    subscription_end_date = Column(DateTime(timezone=True))
    stripe_customer_id = Column(String, unique=True)
    # stripe | apple -- controls cancel/change-tier/manage UI; null treated as stripe if stripe_customer_id set
    billing_provider = Column(String)

    phone_number = Column(String)
    first_scan_completed = Column(Boolean, default=False)

    # iOS APNs device token (hex, no spaces) for server-driven push; cleared on 410 from Apple
    apns_device_token = Column(Text, nullable=True)
    apns_token_updated_at = Column(DateTime(timezone=True), nullable=True)

    onboarding = Column(JSON, default=dict)
    profile = Column(JSON, default=dict)
    schedule_preferences = Column(JSON, default=dict)
    last_progress_prompt_date = Column(String)

    # AI memory -- persistent context the LLM can reference across conversations
    ai_context = Column(Text, default="")
    # Rolling summaries -- last 3 conversation summaries for drift detection
    ai_summaries = Column(JSON, default=list)
    # Persona / tone selected by the user: "default" | "hardcore" | "gentle" | "influencer"
    coaching_tone = Column(String, default="default")

    __table_args__ = (
        Index("idx_app_users_email", email),
        Index("idx_app_users_username", username),
        Index("idx_app_users_is_paid", is_paid),
    )


class PasswordResetOTP(Base):
    """SMS OTP for password reset -- short-lived, single-use."""

    __tablename__ = "password_reset_otps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    phone_normalized = Column(String, nullable=False, index=True)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, default=0)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (Index("idx_password_reset_user_active", "user_id", "consumed_at"),)


class UserCoachingState(Base):
    """Structured coaching state per user -- queryable fields for rules engine"""
    __tablename__ = "user_coaching_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Physical
    weight = Column(Float)
    height = Column(Float)
    body_fat_estimate = Column(Float)

    # Goals & equipment
    primary_goal = Column(String)  # e.g. "jawline", "clear_skin", "physique"
    equipment = Column(JSON, default=list)  # ["mastic_gum", "derma_roller", ...]

    # Tracking
    streak_days = Column(Integer, default=0)
    missed_days = Column(Integer, default=0)
    total_check_ins = Column(Integer, default=0)
    last_check_in = Column(DateTime(timezone=True))
    last_workout = Column(DateTime(timezone=True))

    # Injuries / blockers
    injuries = Column(JSON, default=list)  # [{"area": "jaw", "note": "TMJ pain", "date": "..."}]

    # Tone / style (AI-detected over time)
    preferred_tone = Column(String, default="direct")  # direct, aggressive, chill
    responsiveness = Column(String, default="normal")  # normal, low, high

    # Check-in data (latest)
    last_sleep_hours = Column(Float)
    last_calories = Column(Integer)
    last_mood = Column(String)  # 1-10 or text

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_coaching_state_user_id", user_id),
        Index("idx_coaching_state_missed_days", missed_days),
        Index("idx_coaching_state_streak", streak_days),
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


class ChatConversation(Base):
    """Named chat thread — one row per conversation the user can switch between.

    Legacy chat_history rows (pre-multi-chat) are backfilled into a single
    "Chat history" conversation per user via the startup migration, so the
    new UI surfaces every existing message without losing any history.
    """
    __tablename__ = "chat_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(Text, nullable=False, default="new chat")
    channel = Column(String, nullable=False, default="app")
    is_archived = Column(Boolean, nullable=False, default=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_chat_conversations_user",
            user_id,
            is_archived,
            last_message_at.desc(),
        ),
    )


import contextvars

# Per-request active conversation. process_chat_message() sets this so every
# ChatHistory() constructed inside the request inherits conversation_id without
# having to thread the argument through ~20 scattered call sites.
active_conversation_id: contextvars.ContextVar = contextvars.ContextVar(
    "active_chat_conversation_id", default=None
)


class ChatHistory(Base):
    """AI chat conversation history"""
    __tablename__ = "chat_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    # Nullable so legacy rows keep working; UI filters to the active thread.
    # Backfill migration assigns every pre-existing row to a per-user
    # "Chat history" conversation so nothing disappears from the UI.
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=True,
    )

    def __init__(self, **kwargs):
        # Auto-inject conversation_id from the request-scoped contextvar when
        # the caller didn't specify one. Keeps the 20+ construction sites in
        # api/chat.py unchanged while still writing the new FK.
        if "conversation_id" not in kwargs:
            cv = active_conversation_id.get()
            if cv is not None:
                kwargs["conversation_id"] = cv
        super().__init__(**kwargs)

    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    # "app" = in-app chat UI; "sms" = Twilio SMS thread (not shown in app history)
    channel = Column(String, default="app")
    # JSONB after the RAG split refactor -- stores string chunk refs like
    # "routines:0:abc123". DB migration in db/sqlalchemy.py already converted
    # the column type; the ORM just needed to catch up, otherwise SQLAlchemy
    # casts as BIGINT[] and Postgres rejects the INSERT.
    retrieved_chunk_ids = Column(JSONB, nullable=True)
    partner_rule_ids = Column(ARRAY(BIGINT), nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_chat_user_id", user_id),
        Index("idx_chat_history_conversation", conversation_id, created_at),
        Index("idx_chat_created_at", created_at.desc()),
    )


class ScheduledNotification(Base):
    """Queue for LLM-triggered push notifications.
    The existing APNs worker polls status='pending' rows with scheduled_for <= now.
    """
    __tablename__ = "scheduled_notifications"

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    message = Column(Text, nullable=False)
    # Optional action buttons surfaced in the push -- APNs `category` must be registered on device.
    buttons = Column(ARRAY(String), nullable=True)
    category_id = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | sent | failed | cancelled
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_sched_notif_due", "status", "scheduled_for"),
        Index("idx_sched_notif_user", user_id),
    )


class PartnerRule(Base):
    """Keyword-triggered prompt suffix for partner brand promotion.
    On each chat turn the retriever scans the user message + retrieved chunks
    for trigger_keywords; matches append prompt_suffix to the system prompt.
    """
    __tablename__ = "partner_rules"

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    trigger_keywords = Column(ARRAY(String), nullable=False)
    prompt_suffix = Column(Text, nullable=False)
    active = Column(Boolean, default=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (Index("idx_partner_rules_active", active),)


class UserProgressPhoto(Base):
    """Daily progress photos for users"""
    __tablename__ = "user_progress_photos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    # app = in-app upload; sms = Twilio MMS webhook
    source = Column(String, default="app")
    # Optional overall face rating (e.g. from same-day face scan) shown on progress grid
    face_rating = Column(Float, nullable=True)

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


class RagDocument(Base):
    """Chunked knowledge documents for RAG retrieval, namespaced by maxx_id."""
    __tablename__ = "rag_documents"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    maxx_id     = Column(String(50),  nullable=False, index=True)   # "fitmax", "skinmax", …
    doc_title   = Column(String(255), nullable=False)
    chunk_index = Column(Integer,     nullable=False, default=0)
    content     = Column(Text,        nullable=False)
    # pgvector column -- nullable so rows can be added/edited without an embedding vector
    embedding   = Column(Vector(1536), nullable=True) if _PGVECTOR_AVAILABLE else Column(Text, nullable=True)
    metadata_   = Column("metadata", JSON, default=dict)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at  = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class ChannelMessageReport(Base):
    """User reports on channel (forum) messages -- App Review UGC moderation trail."""

    __tablename__ = "channel_message_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_message_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    channel_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    reporter_user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    reported_user_id = Column(UUID(as_uuid=True), nullable=False)
    reason = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("channel_message_id", "reporter_user_id", name="uq_channel_message_report_reporter"),
    )


class SystemPrompt(Base):
    """LLM system prompt bodies managed in DB; key matches PromptKey constants."""

    __tablename__ = "system_prompts"

    key         = Column(String, primary_key=True)
    content     = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_active   = Column(Boolean, default=True, nullable=False)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime(timezone=True), default=datetime.utcnow,
                         onupdate=datetime.utcnow, nullable=False)


class UserOnairosConnection(Base):
    """Per-user Onairos consent handoff + cached trait snapshot.

    One row per user (unique on user_id). Created/updated on SDK re-consent;
    soft-deleted via revoked_at when the user disconnects. The coaching context
    builder reads traits_cached to append a MEMORY SLOT of traits/preferences
    without calling the Onairos API on every chat turn.
    """

    __tablename__ = "user_onairos_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    api_url = Column(Text, nullable=False)
    access_token = Column(Text, nullable=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    approved_requests = Column(JSONB, nullable=False, default=dict)
    user_basic = Column(JSONB, nullable=True)

    traits_cached = Column(JSONB, nullable=True)
    traits_cached_at = Column(DateTime(timezone=True), nullable=True)

    connected_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow,
                        onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_user_onairos_connections_user_id", user_id),
    )

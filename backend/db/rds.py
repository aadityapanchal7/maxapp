"""
SQLAlchemy Database Connection Manager for AWS RDS
Async PostgreSQL for shared/multi-user data
"""

import asyncio
import logging
import time

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from typing import AsyncGenerator

from config import settings

logger = logging.getLogger(__name__)


# Create async engine for AWS RDS. Real RDS requires SSL; a LOCAL stand-in
# (host=localhost, used for dev/testing the shared-DB features) rejects the
# SSL upgrade — so only require it for non-local hosts.
_RDS_IS_LOCAL = (settings.aws_rds_host or "").strip() in ("localhost", "127.0.0.1", "::1")
rds_engine = create_async_engine(
    settings.aws_rds_db_url,
    echo=getattr(settings, "sql_echo", False),
    pool_size=5,
    max_overflow=5,
    pool_recycle=180,
    pool_timeout=10,
    pool_pre_ping=True,
    connect_args={
        # 2s, not 10. RDS is an OPTIONAL enrichment store — every endpoint that
        # touches it has a first-class fallback. When the host is unreachable
        # (security group change, instance retired) a 10s connect timeout turned
        # `GET /maxes` — which Home, Explore and Profile all fetch — into a
        # 10.8s request. The wait buys nothing: we fall back either way.
        "timeout": 2,
        **({} if _RDS_IS_LOCAL else {"ssl": "require"}),
        "server_settings": {"application_name": "maxapp_rds"},
    },
)

# ─── Circuit breaker ─────────────────────────────────────────────────────────
# Even a 2s timeout is 2s of a user's life, paid on EVERY request, while RDS is
# down. After a failure we stop dialling for a cooldown and yield None instantly
# (the same thing a mis-configured environment yields), so callers take their
# fallback path with zero latency. One probe per cooldown re-opens the circuit
# by itself, so recovery needs no deploy.
_RDS_COOLDOWN_SECONDS = 120.0
_rds_open_until: float = 0.0        # monotonic deadline; 0 = circuit closed
_rds_probe_lock = asyncio.Lock()


def _rds_circuit_open() -> bool:
    return time.monotonic() < _rds_open_until


def _trip_rds_circuit(exc: BaseException) -> None:
    global _rds_open_until
    first = not _rds_circuit_open()
    _rds_open_until = time.monotonic() + _RDS_COOLDOWN_SECONDS
    if first:
        logger.warning(
            "RDS unreachable (%s: %s) — serving fallbacks for %.0fs before retrying.",
            type(exc).__name__, exc, _RDS_COOLDOWN_SECONDS,
        )


def rds_circuit_state() -> dict:
    """Diagnostics for /health — is RDS being skipped, and for how long."""
    remaining = max(0.0, _rds_open_until - time.monotonic())
    return {"open": remaining > 0, "cooldown_remaining_s": round(remaining, 1)}

# Session factory
RDSSessionLocal = async_sessionmaker(
    rds_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_rds_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection for RDS database sessions.
    Usage: rds_db: AsyncSession = Depends(get_rds_db)

    Raises 503 (instead of the cryptic asyncpg "password authentication
    failed" connection error) when RDS is not configured. Endpoints that
    can degrade gracefully should use `get_rds_db_optional` instead.
    """
    if not (settings.aws_rds_password or "").strip():
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="This feature requires the shared (RDS) database, which is not configured in this environment.",
        )
    async with RDSSessionLocal() as session:
        yield session


async def get_rds_db_optional() -> AsyncGenerator["AsyncSession | None", None]:
    """
    Optional RDS session — yields None when RDS is not configured (no password).
    Endpoints should use `if rds_db:` before querying RDS.

    Use only a single `yield session` inside `async with` (no extra try/finally/close),
    so FastAPI can inject athrow() into the dependency generator safely.
    """
    if not (settings.aws_rds_password or "").strip():
        yield None
        return

    # Circuit open → behave exactly like "not configured": instant None, and
    # the endpoint serves its fallback. No dial, no timeout, no user-visible wait.
    if _rds_circuit_open():
        yield None
        return

    # Connect EAGERLY rather than letting the first query inside the endpoint
    # raise: a lazily-connected session hands the failure to the caller's
    # try/except, which swallows it WITHOUT tripping the breaker — so every
    # subsequent request would pay the timeout again.
    #
    # Only the CONNECT is wrapped. FastAPI injects endpoint exceptions back into
    # this generator at the `yield`, so a try/except spanning the yield would
    # both mis-trip the breaker and try to yield twice.
    session = RDSSessionLocal()
    try:
        await session.connection()
    except Exception as e:
        _trip_rds_circuit(e)
        try:
            await session.close()
        except Exception:
            pass
        yield None
        return

    async with session:
        yield session


async def init_rds_db():
    """Initialize RDS database tables.

    No-op when RDS is not configured (no password) — the rest of the app
    runs fine on Supabase alone, and `get_rds_db_optional` yields None
    so any RDS-dependent endpoint gracefully skips. Avoids spamming
    "password authentication failed" warnings on local dev.
    """
    if not (settings.aws_rds_password or "").strip():
        print("[INFO] RDS not configured (no AWS_RDS_PASSWORD) — skipping RDS init.")
        return
    try:
        from models.rds_models import Base
        async with rds_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _run_rds_column_migrations()
        print("[OK] RDS tables created/verified")
    except Exception as e:
        print(f"[WARNING] Could not initialize RDS database: {e}")
        print("[INFO] Ensure AWS RDS is accessible from deployment environment.")


async def _run_rds_column_migrations():
    """Add missing columns to maxes table (safe to run repeatedly)."""
    migrations = [
        "ALTER TABLE maxes ADD COLUMN IF NOT EXISTS protocols JSONB DEFAULT '{}'",
        "ALTER TABLE maxes ADD COLUMN IF NOT EXISTS schedule_rules JSONB DEFAULT '{}'",
        "ALTER TABLE maxes ADD COLUMN IF NOT EXISTS concern_mapping JSONB DEFAULT '{}'",
        "ALTER TABLE maxes ADD COLUMN IF NOT EXISTS concern_question TEXT",
        "ALTER TABLE maxes ADD COLUMN IF NOT EXISTS concerns JSONB DEFAULT '[]'",
        "ALTER TABLE maxes ADD COLUMN IF NOT EXISTS protocol_prompt_template TEXT",

        # ------------------------------------------------------------------
        # Forums v2 (classic threads) — safe additive migrations
        # ------------------------------------------------------------------
        "ALTER TABLE forum_categories ADD COLUMN IF NOT EXISTS description TEXT",
        "ALTER TABLE forum_categories ADD COLUMN IF NOT EXISTS \"order\" INTEGER DEFAULT 0",
        "ALTER TABLE forum_categories ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",

        "ALTER TABLE forum_subforums ADD COLUMN IF NOT EXISTS description TEXT",
        "ALTER TABLE forum_subforums ADD COLUMN IF NOT EXISTS \"order\" INTEGER DEFAULT 0",
        "ALTER TABLE forum_subforums ADD COLUMN IF NOT EXISTS access_tier VARCHAR DEFAULT 'public'",
        "ALTER TABLE forum_subforums ADD COLUMN IF NOT EXISTS is_read_only BOOLEAN DEFAULT false",
        "ALTER TABLE forum_subforums ADD COLUMN IF NOT EXISTS created_by UUID",
        "ALTER TABLE forum_subforums ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",

        # Older dev schema used forum_id; keep it but add subforum_id.
        "ALTER TABLE forum_threads ADD COLUMN IF NOT EXISTS subforum_id UUID",
        "ALTER TABLE forum_threads ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'",
        "ALTER TABLE forum_threads ADD COLUMN IF NOT EXISTS is_sticky BOOLEAN DEFAULT false",
        "ALTER TABLE forum_threads ADD COLUMN IF NOT EXISTS is_locked BOOLEAN DEFAULT false",
        "ALTER TABLE forum_threads ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0",
        "ALTER TABLE forum_threads ADD COLUMN IF NOT EXISTS reply_count INTEGER DEFAULT 0",
        "ALTER TABLE forum_threads ADD COLUMN IF NOT EXISTS last_post_at TIMESTAMPTZ DEFAULT now()",
        "ALTER TABLE forum_threads ADD COLUMN IF NOT EXISTS last_post_user_id UUID",
        "ALTER TABLE forum_threads ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",
        # Legacy compatibility: v2 thread creation does not use these chat-era fields.
        "ALTER TABLE forum_threads ALTER COLUMN forum_id DROP NOT NULL",
        "ALTER TABLE forum_threads ALTER COLUMN content DROP NOT NULL",
        # Backfill subforum_id from forum_id when present
        "UPDATE forum_threads SET subforum_id = forum_id WHERE subforum_id IS NULL AND forum_id IS NOT NULL",

        "ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS entities JSONB DEFAULT '{}'",
        "ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS attachment_url TEXT",
        "ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS attachment_type VARCHAR",
        "ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS parent_post_id UUID",
        "ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS score INTEGER DEFAULT 0",
        "ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS upvotes INTEGER DEFAULT 0",
        "ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS downvotes INTEGER DEFAULT 0",
        "ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",
        "ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now()",

        "ALTER TABLE forum_post_votes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",
        "ALTER TABLE forum_thread_watches ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",

        "ALTER TABLE forum_notifications ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'",
        "ALTER TABLE forum_notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT false",
        "ALTER TABLE forum_notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",

        "ALTER TABLE forum_post_reports ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'open'",
        "ALTER TABLE forum_post_reports ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",

        # ------------------------------------------------------------------
        # Creator-maxx channels: per-maxx members-only rooms in the legacy
        # channel table. Uniqueness moves from global unique(name/slug) to
        # PARTIAL indexes (global-only when maxx_id IS NULL; per-maxx name
        # otherwise) — a second creator's "#general" would violate the old
        # constraints. DROP CONSTRAINT covers the standard autogenerated
        # names; IF EXISTS keeps this idempotent + safe where names differ
        # (channel creation also catches IntegrityError as a belt-and-braces).
        # ------------------------------------------------------------------
        "ALTER TABLE forums ADD COLUMN IF NOT EXISTS maxx_id VARCHAR",
        "ALTER TABLE forums ADD COLUMN IF NOT EXISTS creator_id UUID",
        "ALTER TABLE forums ADD COLUMN IF NOT EXISTS who_can_post VARCHAR DEFAULT 'members'",
        "ALTER TABLE forums ADD COLUMN IF NOT EXISTS allow_replies BOOLEAN DEFAULT true",
        "ALTER TABLE forums ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT false",
        "ALTER TABLE forums DROP CONSTRAINT IF EXISTS forums_name_key",
        "ALTER TABLE forums DROP CONSTRAINT IF EXISTS forums_slug_key",
        "CREATE INDEX IF NOT EXISTS idx_forums_maxx ON forums (maxx_id) WHERE maxx_id IS NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_forums_global_name ON forums (name) WHERE maxx_id IS NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_forums_global_slug ON forums (slug) WHERE maxx_id IS NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_forums_maxx_name ON forums (maxx_id, lower(name)) WHERE maxx_id IS NOT NULL",
    ]
    unique_constraints = [
        ("forum_post_reports", "uq_forum_post_report_reporter", "post_id, reporter_user_id"),
    ]
    try:
        async with rds_engine.begin() as conn:
            await conn.execute(text("SET lock_timeout = '5s'"))
            for sql in migrations:
                await conn.execute(text(sql))
            for table, name, cols in unique_constraints:
                await conn.execute(text(
                    f"DO $$ BEGIN "
                    f"ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({cols}); "
                    f"EXCEPTION WHEN duplicate_table THEN NULL; END $$;"
                ))
        print("[OK] RDS column migrations applied")
    except Exception as e:
        print(f"[INFO] RDS column migration note: {e}")


async def close_rds_db():
    """Close RDS database connections"""
    try:
        await rds_engine.dispose()
        print("[OK] RDS connection closed")
    except Exception:
        pass

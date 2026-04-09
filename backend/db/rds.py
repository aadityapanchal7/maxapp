"""
SQLAlchemy Database Connection Manager for AWS RDS
Async PostgreSQL for shared/multi-user data
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from typing import AsyncGenerator

from config import settings


# Create async engine for AWS RDS
rds_engine = create_async_engine(
    settings.aws_rds_db_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=5,
    pool_recycle=180,
    pool_timeout=10,
    pool_pre_ping=True,
    connect_args={
        "timeout": 10,
        "ssl": "require",
        "server_settings": {"application_name": "maxapp_rds"},
    },
)

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
    Dependency injection for RDS database sessions
    Usage: rds_db: AsyncSession = Depends(get_rds_db)
    """
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

    async with RDSSessionLocal() as session:
        yield session


async def init_rds_db():
    """Initialize RDS database tables"""
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

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
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={
        "timeout": 30,
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
        try:
            yield session
        finally:
            await session.close()


async def get_rds_db_optional() -> AsyncGenerator["AsyncSession | None", None]:
    """
    Optional RDS session — yields None if RDS is unavailable (e.g. not configured).
    Use for endpoints that can fall back to code when RDS fails.
    """
    try:
        async with RDSSessionLocal() as session:
            yield session
    except Exception:
        yield None


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
    ]
    try:
        async with rds_engine.begin() as conn:
            for sql in migrations:
                await conn.execute(text(sql))
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

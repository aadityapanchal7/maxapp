"""
SQLAlchemy Database Connection Manager for AWS RDS
Async PostgreSQL for shared/multi-user data
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
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
        "server_settings": {"application_name": "cannonapp_rds"}
    }
)

# Session factory
RDSSessionLocal = async_sessionmaker(
    rds_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
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


async def init_rds_db():
    """Initialize RDS database tables"""
    try:
        from models.rds_models import Base
        async with rds_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[OK] RDS database tables created/verified")
    except Exception as e:
        print(f"[WARNING] Could not initialize RDS database: {e}")
        print("[INFO] Ensure AWS RDS is accessible from deployment environment.")


async def close_rds_db():
    """Close RDS database connections"""
    try:
        await rds_engine.dispose()
        print("[OK] RDS database connection closed")
    except Exception:
        pass

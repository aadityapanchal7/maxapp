"""
Max App - Configuration Management
Loads environment variables with validation using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # MongoDB
    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    mongodb_database: str = Field(default="cannon_db")

    # Supabase (user-specific data)
    supabase_url: str = Field(default="https://your-project.supabase.co")
    supabase_anon_key: str = Field(default="")
    supabase_service_role_key: str = Field(default="")
    supabase_db_host: str = Field(default="localhost")
    supabase_db_port: int = Field(default=5432)
    supabase_db_user: str = Field(default="postgres")
    supabase_db_password: str = Field(default="")
    supabase_db_name: str = Field(default="postgres")
    # Keep small on Session pooler (5432). If you see MaxClientsInSessionMode:
    # - Switch SUPABASE_DB_PORT to 6543 (Transaction pooler in Supabase Dashboard), and/or
    # - Set SUPABASE_DB_POOL_SIZE=1 and SUPABASE_DB_MAX_OVERFLOW=0 on Render.
    supabase_db_pool_size: int = Field(default=1)
    supabase_db_max_overflow: int = Field(default=0)

    # AWS RDS (shared data)
    aws_rds_host: str = Field(default="localhost")
    aws_rds_port: int = Field(default=5432)
    aws_rds_user: str = Field(default="postgres")
    aws_rds_password: str = Field(default="")
    aws_rds_database: str = Field(default="cannon_shared")
    
    # JWT Authentication
    jwt_secret_key: str = Field(default="change-this-secret-key")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=1440)  # 24 hours
    jwt_refresh_token_expire_days: int = Field(default=300)      # ~10 months
    
    # LLM provider: "gemini" (default) or "openai"
    llm_provider: str = Field(default="gemini")
    # Google Gemini
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")
    # OpenAI (when llm_provider=openai)
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_vision_model: str = Field(
        default="",
        description="Vision-capable model for scans/chat images; defaults to openai_model if empty",
    )
    
    # External Facial Analysis API (cannon_facial_analysis service)
    facial_analysis_api_url: str = Field(default="http://13.236.183.141:8001/api")
    
    # Stripe
    stripe_secret_key: str = Field(default="")
    stripe_publishable_key: str = Field(default="")
    stripe_webhook_secret: str = Field(default="")
    stripe_price_id: str = Field(default="")
    stripe_basic_price_id: str = Field(default="")
    stripe_premium_price_id: str = Field(default="")
    subscription_price_monthly: float = Field(default=9.99)
    subscription_currency: str = Field(default="usd")
    
    # Sendblue (iMessage / SMS) — https://sendblue.com/
    sendblue_api_key_id: str = Field(default="", description="sb-api-key-id header")
    sendblue_api_secret_key: str = Field(default="", description="sb-api-secret-key header")
    sendblue_from_number: str = Field(default="", description="Your Sendblue line E.164, e.g. +16468304204")
    sendblue_webhook_secret: str = Field(
        default="",
        description="Optional: must match Sendblue webhook secret header for /api/sendblue/receive",
    )
    # DEV ONLY: set SMS_SCHEDULER_TEST_FAST_MODE=true — 1-min scheduler ticks, bypass clock windows so SMS
    # fires immediately; coaching + weekly send at most once per user until you restart the API process.
    sms_scheduler_test_fast_mode: bool = Field(default=False)
    
    # AWS S3
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    aws_s3_bucket: str = Field(default="cannon-app-uploads")
    aws_s3_region: str = Field(default="us-east-1")
    # Remote LLM prompts (optional). If empty, bundled Python strings are used.
    # Upload objects to: s3://{prompts_s3_bucket}/{prompts_s3_prefix}/{key}.md (or .txt)
    prompts_s3_bucket: str = Field(
        default="",
        description="S3 bucket for chat/coaching prompt bodies; IAM needs s3:GetObject",
    )
    prompts_s3_prefix: Optional[str] = Field(
        default=None,
        description=(
            "S3 key prefix, no leading/trailing slash (e.g. prompts/prod). "
            "If unset/null, defaults to prompts/prod. Set env PROMPTS_S3_PREFIX= (empty) for bucket root."
        ),
    )
    prompts_s3_region: Optional[str] = Field(
        default=None,
        description=(
            "Region for PROMPTS_S3_BUCKET (e.g. us-east-1). "
            "If unset, falls back to AWS_S3_REGION."
        ),
    )
    
    # Application
    app_name: str = Field(default="Max")
    app_env: str = Field(default="development")
    debug: bool = Field(default=True)
    api_version: str = Field(default="v1")
    
    # CORS — comma-separated; Expo web uses :8081 (also matched by localhost regex in main.py when not production)
    cors_origins: str = Field(
        default=(
            "http://localhost:3000,http://localhost:8081,http://127.0.0.1:8081,"
            "http://localhost:19006,http://127.0.0.1:19006"
        )
    )
    
    # Rate Limiting
    rate_limit_requests: int = Field(default=100)
    rate_limit_period_seconds: int = Field(default=60)
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def supabase_db_url(self) -> str:
        """Supabase Postgres connection string"""
        return (
            f"postgresql+asyncpg://{self.supabase_db_user}:{self.supabase_db_password}"
            f"@{self.supabase_db_host}:{self.supabase_db_port}/{self.supabase_db_name}"
        )

    @property
    def aws_rds_db_url(self) -> str:
        """AWS RDS Postgres connection string"""
        return (
            f"postgresql+asyncpg://{self.aws_rds_user}:{self.aws_rds_password}"
            f"@{self.aws_rds_host}:{self.aws_rds_port}/{self.aws_rds_database}"
        )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    return Settings()


# Export settings instance
settings = get_settings()

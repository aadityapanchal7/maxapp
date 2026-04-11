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
    # Session pooler (5432) enforces a tiny client cap → MaxClientsInSessionMode if pool+overflow
    # exceeds it. Defaults are safe for 5432; for Transaction pooler (6543) raise via env, e.g.
    # SUPABASE_DB_POOL_SIZE=5 and SUPABASE_DB_MAX_OVERFLOW=5.
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
    
    # Stripe — secret key stays server-side; publishable key is only for reference / admin.
    stripe_secret_key: str = Field(default="")
    stripe_publishable_key: str = Field(default="")
    stripe_webhook_secret: str = Field(default="")
    # Legacy embedded-checkout price (kept for backward compat; not used by native flow)
    stripe_price_id: str = Field(default="")
    stripe_basic_price_id: str = Field(default="")
    stripe_premium_price_id: str = Field(default="")
    subscription_price_monthly: float = Field(default=9.99)
    subscription_currency: str = Field(default="usd")
    # Weekly subscription prices — create as *recurring / weekly* in Stripe Dashboard
    stripe_price_id_weekly_basic: str = Field(
        default="",
        description="Stripe Price ID for Chadlite weekly subscription (e.g. price_xxx)",
    )
    stripe_price_id_weekly_premium: str = Field(
        default="",
        description="Stripe Price ID for Chad weekly subscription (e.g. price_xxx)",
    )
    # Must match the API version expected by @stripe/stripe-react-native for EphemeralKey.
    # Check Stripe RN SDK changelog when upgrading the mobile package.
    stripe_ephemeral_key_api_version: str = Field(default="2024-12-18.acacia")
    
    # Sendblue (iMessage / SMS) — https://sendblue.com/
    sendblue_api_key_id: str = Field(default="", description="sb-api-key-id header")
    sendblue_api_secret_key: str = Field(default="", description="sb-api-secret-key header")
    sendblue_from_number: str = Field(default="", description="Your Sendblue line E.164, e.g. 16468304204")
    sendblue_webhook_secret: str = Field(
        default="",
        description="Optional: must match Sendblue webhook secret header for /api/sendblue/receive",
    )
    # DEV ONLY: set SMS_SCHEDULER_TEST_FAST_MODE=true — 1-min scheduler ticks, bypass clock windows so SMS
    # fires immediately; coaching  weekly send at most once per user until you restart the API process.
    sms_scheduler_test_fast_mode: bool = Field(default=False)

    # Apple Push Notification service (direct HTTP/2) — .p8 key PEM or base64-of-PEM
    apns_auth_key_p8: str = Field(default="", description="APNs Auth Key PEM or base64-encoded PEM")
    apns_key_id: str = Field(default="", description="10-char Key ID from Apple Developer")
    apns_team_id: str = Field(default="", description="Apple Team ID (iss claim)")
    apns_bundle_id: str = Field(default="com.cannon.mobile", description="apns-topic / bundle id")
    apns_use_sandbox: bool = Field(
        default=False,
        description="True → api.sandbox.push.apple.com (Xcode debug builds only); False → production (TestFlight / App Store)",
    )
    
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
        """Parse CORS origins string into list.

        In development (or when debug is on), merge common Expo web ports (8081–8095, etc.)
        so the browser Origin header matches even if Metro uses 8082 after a port conflict.
        Production with debug off uses only the explicit env list.
        """
        parsed = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        allow_dev_extras = self.app_env.strip().lower() != "production" or self.debug
        if not allow_dev_extras:
            return parsed
        dev_extras: List[str] = []
        for port in range(8081, 8096):
            dev_extras.extend(
                [
                    f"http://localhost:{port}",
                    f"http://127.0.0.1:{port}",
                    f"http://[::1]:{port}",
                ]
            )
        for port in (19000, 19006, 8080, 3000):
            dev_extras.extend(
                [
                    f"http://localhost:{port}",
                    f"http://127.0.0.1:{port}",
                    f"http://[::1]:{port}",
                ]
            )
        return list(dict.fromkeys(parsed + dev_extras))

    @property
    def supabase_db_url(self) -> str:
        """Supabase Postgres connection string.

        Do NOT append ?pgbouncer=true — asyncpg doesn't understand it and
        crashes with 'unexpected keyword argument'. PgBouncer-specific
        settings (statement_cache_size=0) are handled in connect_args instead.
        """
        host = self.supabase_db_host.split("?")[0].split("/")[0]
        return (
            f"postgresql+asyncpg://{self.supabase_db_user}:{self.supabase_db_password}"
            f"@{host}:{self.supabase_db_port}/{self.supabase_db_name}"
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


_DEFAULT_JWT_SECRET = "change-this-secret-key"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    s = Settings()
    # Refuse to boot in production with the default JWT secret — that would let
    # anyone mint valid tokens for any user. Dev/test is allowed to keep the
    # default so local contributors aren't blocked.
    if s.app_env.strip().lower() == "production" and s.jwt_secret_key == _DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET_KEY is still the default placeholder in production. "
            "Set a strong random value (e.g. `python -c 'import secrets; print(secrets.token_urlsafe(48))'`) "
            "in the environment before starting the server."
        )
    return s


# Export settings instance
settings = get_settings()

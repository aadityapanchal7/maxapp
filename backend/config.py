"""
Cannon App - Configuration Management
Loads environment variables with validation using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # MongoDB
    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    mongodb_database: str = Field(default="cannon_db")
    
    # JWT Authentication
    jwt_secret_key: str = Field(default="change-this-secret-key")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=1440)  # 24 hours
    jwt_refresh_token_expire_days: int = Field(default=300)      # ~10 months
    
    # Google Gemini
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")
    
    # External Facial Analysis API (cannon_facial_analysis service)
    facial_analysis_api_url: str = Field(default="http://localhost:8001/api")
    
    # Stripe
    stripe_secret_key: str = Field(default="")
    stripe_publishable_key: str = Field(default="")
    stripe_webhook_secret: str = Field(default="")
    stripe_price_id: str = Field(default="")
    subscription_price_monthly: float = Field(default=9.99)
    subscription_currency: str = Field(default="usd")
    
    # AWS S3
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    aws_s3_bucket: str = Field(default="cannon-app-uploads")
    aws_s3_region: str = Field(default="us-east-1")
    
    # Application
    app_name: str = Field(default="Cannon")
    app_env: str = Field(default="development")
    debug: bool = Field(default=True)
    api_version: str = Field(default="v1")
    
    # CORS
    cors_origins: str = Field(default="http://localhost:3000,http://localhost:8081")
    
    # Rate Limiting
    rate_limit_requests: int = Field(default=100)
    rate_limit_period_seconds: int = Field(default=60)
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    return Settings()


# Export settings instance
settings = get_settings()

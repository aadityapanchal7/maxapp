"""
Max - Configuration Management
Loads environment variables with validation using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import os

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent


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
    # Connection-pool sizing. Left as None so db/sqlalchemy.py picks values that
    # match the pooler MODE: small for Session pooler (5432, ~15 global client
    # cap → MaxClientsInSessionMode if exceeded), large for the Transaction
    # pooler / Supavisor (6543, multiplexes thousands of clients). Set these env
    # vars to pin explicit values; otherwise the mode-aware defaults apply.
    # Production recommendation: SUPABASE_DB_PORT=6543.
    supabase_db_pool_size: Optional[int] = Field(default=None)
    supabase_db_max_overflow: Optional[int] = Field(default=None)

    # Social profile lookup (creator applications) — pulls public follower
    # count + avatar for a given Instagram/TikTok handle. Provider-agnostic:
    # set rapidapi_key and (optionally) override the hosts to any compatible
    # RapidAPI scraper. When no key is set the flow still works — it just
    # stores the handle/canonical URL without enriched stats.
    social_lookup_provider: str = Field(default="rapidapi")
    rapidapi_key: str = Field(default="")
    rapidapi_ig_host: str = Field(default="instagram-scraper-api2.p.rapidapi.com")
    rapidapi_tt_host: str = Field(default="tiktok-scraper7.p.rapidapi.com")

    # Creator social OAuth (Instagram / TikTok sign-in during application).
    # When credentials are empty in dev, the flow uses a local mock consent page.
    social_oauth_redirect_base: str = Field(
        default="http://localhost:8000/api",
        description="Base URL for OAuth callbacks, e.g. https://api.usemaxapp.com/api",
    )
    instagram_client_id: str = Field(default="")
    instagram_client_secret: str = Field(default="")
    instagram_scopes: str = Field(default="instagram_business_basic")
    tiktok_client_key: str = Field(default="")
    tiktok_client_secret: str = Field(default="")
    tiktok_scopes: str = Field(default="user.info.basic,user.info.profile,user.info.stats")
    # When True, creator applications require OAuth-linked Instagram or TikTok.
    # Set False while Meta/TikTok credentials are unset; flip True for production verify.
    creator_social_oauth_required: bool = Field(default=True)

    # Post for Me — hosted per-user IG/TikTok OAuth linking (brings its own
    # Meta/TikTok-approved apps, so no direct app review needed). When postforme_key
    # is set it becomes the creator-social provider, superseding the direct
    # instagram_/tiktok_ credentials above. One key is shared across products
    # (e.g. Yunicorn); users are namespaced by external_id = "{prefix}:{user_id}".
    postforme_key: str = Field(default="")
    postforme_base: str = Field(default="https://api.postforme.dev/v1")
    postforme_external_id_prefix: str = Field(default="maxapp")
    # Quickstart Post for Me projects REJECT redirect_url_override; the account is
    # instead recovered by polling /social-accounts by external_id (what /status
    # does). Flip True only on a full (non-Quickstart) project to auto-return to the app.
    postforme_allow_redirect_override: bool = Field(default=False)

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
    
    # LLM provider: "huggingface" (default), "gemini", "openai", or "mistral".
    # huggingface routes chat completions through a Hugging Face Dedicated
    # Inference Endpoint via the OpenAI SDK compatibility layer (model="tgi").
    llm_provider: str = Field(default="huggingface")
    # Hugging Face Dedicated Inference Endpoint -- OpenAI-compatible /v1
    hf_token: str = Field(default="", description="Hugging Face API token for the dedicated endpoint")
    hf_endpoint_url: str = Field(
        default="https://pr83qgnhfqomb51f.us-east-1.aws.endpoints.huggingface.cloud/v1",
        description="HF dedicated endpoint base URL (must end in /v1 for OpenAI compat)",
    )
    hf_model: str = Field(
        default="tgi",
        description="HF TGI uses the literal string 'tgi' as the model name in chat completions",
    )
    # Google Gemini -- still required for face-scan vision (HF TGI text endpoint can't do images)
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")
    # Anthropic Claude -- used for face-scan vision when LLM_PROVIDER=claude
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-haiku-4-5")

    # --- Dynamic per-user onboarding (DYNAMIC_ONBOARDING_SPEC.md) ------------
    # All default OFF; the LLM path requires slot_prefill. With every flag off,
    # onboarding stays byte-for-byte today's fixed-question state machine.
    slot_prefill_enabled: bool = Field(
        default=False,
        description="Deterministic cross-Max dedup (prefill + missing_required). Ship/enable first.",
    )
    dynamic_questions_enabled: bool = Field(
        default=False,
        description="LLM question phrasing/ordering. Requires slot_prefill_enabled.",
    )
    dynamic_questions_shadow: bool = Field(
        default=False,
        description="Log would-skip/would-ask diffs without enforcing the LLM plan.",
    )
    dynamic_questions_model: str = Field(default="claude-haiku-4-5")
    dynamic_questions_cache_ttl_s: int = Field(default=600)
    slot_default_min_confidence: float = Field(default=0.6)
    slot_freshness_ttl_days: int = Field(default=180)

    # OpenAI -- still required for face-scan vision fallback when Gemini key is missing
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_vision_model: str = Field(
        default="",
        description="Vision-capable model for scans/chat images; defaults to openai_model if empty",
    )
    # Mistral (legacy provider; kept for optional fallback only)
    mistral_api_key: str = Field(default="")
    mistral_model: str = Field(default="mistral-large-latest")
    # Per-provider HTTP timeout in seconds (applies to each individual API call).
    # With fallback: worst-case for one LLM pass = llm_timeout_seconds * 2.
    llm_timeout_seconds: int = Field(default=25)
    # Max output tokens for schedule adaptation LLM only (full JSON days). Higher reduces
    # truncation on dense schedules; cap is the model's own max (e.g. OpenAI completion limit).
    schedule_adapt_max_output_tokens: int = Field(default=16384)

    # DB-backed RAG / retrieval budgets
    rag_top_k: int = Field(default=4, description="How many chunks to retrieve per query")
    rag_score_threshold: float = Field(
        default=0.35,
        description="Min BM25 score to keep a retrieved chunk. Below this, retrieval is ignored.",
    )
    rag_hybrid_enabled: bool = Field(
        default=True,
        description="Enable hybrid retrieval (BM25 + vector + RRF).",
    )
    rag_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model used for hybrid RAG vector search.",
    )
    rag_embedding_dimensions: int = Field(
        default=1536,
        description="Embedding vector dimensions for rag_documents.embedding.",
    )
    rag_bm25_k: int = Field(
        default=12,
        description="BM25 candidate pool size before RRF fusion.",
    )
    rag_vector_k: int = Field(
        default=12,
        description="Vector candidate pool size before RRF fusion.",
    )
    rag_rrf_k: int = Field(
        default=60,
        description="RRF smoothing constant for hybrid rank fusion.",
    )

    # LangGraph chat orchestration -- when true, chat uses services/lc_graph.py
    # (intent classifier -> guardrail -> parallel RAG -> trim -> agent -> finalize).
    # When false, chat.py calls run_chat_agent directly (legacy path).
    chat_use_langgraph: bool = Field(default=False)

    # Personalized framing (Phase 2): when true, build_personalization_brief
    # appends explicit human-voice / accountability guidance to the brief header
    # (speak like a coach who remembers and holds them to it; tie motivation to
    # their stated values/why/deadline; let interests color examples; never
    # invent). Purely additive prompt guidance — collects no new data. Default
    # OFF so the brief stays byte-identical until the guidance is validated.
    personalized_framing: bool = Field(default=False)

    # Commute-aware placement (Phase 3): when true, the human-time placement
    # engine treats the user's stated commute (work_start - commute .. work_start
    # and work_end .. work_end + commute) as a PROTECTED span, so hands-on tasks
    # (skincare, workouts) don't land mid-transit. Bounded + additive. Default
    # OFF so existing schedules are byte-identical until validated.
    commute_aware_placement: bool = Field(default=False)

    # Warmer notification copy (Phase 4): when true, a few NEW template variants
    # that reference the user's stated why / active plan warmly join the rotation
    # (the {why}/{plan} slots already exist). They each require their signal, pass
    # the taste bar at import, and DO NOT change cadence/cap/interval/backoff.
    # Default OFF so the rotation is byte-identical until validated.
    personalized_notif_copy: bool = Field(default=False)

    # Referral / promo code system (RALPH_REFERRAL). All default OFF so the app is
    # byte-identical to today until enabled.
    #  - referrals_enabled gates the whole feature (validate/redeem endpoints +
    #    the client code field). When OFF the endpoints 404 and the field hides.
    #  - referral_discounts_enabled gates the discount SEAM (Apple Offer Code /
    #    Stripe promo); OFF or with unset ids, discount codes degrade to
    #    "recognized, discount coming" and NEVER charge a wrong amount.
    #  - referral_rewards_enabled gates the referrer-reward hook.
    referrals_enabled: bool = Field(default=True)
    referral_discounts_enabled: bool = Field(default=False)
    referral_rewards_enabled: bool = Field(default=False)
    # Creator-maxx card art: server-side Higgsfield auto-generation at approval.
    # OFF by default — art is attached manually via POST /admin/creators/{id}/art
    # (see services/creator_art.py for the intended pipeline).
    creator_art_autogen_enabled: bool = Field(default=False)
    chat_max_context_tokens: int = Field(
        default=8000,
        description="Hard ceiling for history + retrieved chunks tokens in the agent prompt.",
    )
    chat_max_coaching_context_tokens: int = Field(
        default=1800,
        description="Hard cap for the serialized coaching_context blob added to prompts.",
    )
    chat_max_system_prompt_tokens: int = Field(
        default=4096,
        # The fully-assembled agent prompt (base + VOICE + product/MCQ/web rules +
        # persona + diet ABSOLUTE RULES + length) is ~3.3k-3.6k tokens for a real
        # user with onboarding facts. The old 3200 cap trimmed EVERY such user,
        # gutting the persona/voice/product rules. 4096 fits the full prompt so
        # nothing critical is dropped; the trim is now only a safety net for
        # pathologically large briefs.
        description="Hard cap for the final system prompt after context injection.",
    )

    # Onairos personalization — optional partner-level config. The mobile SDK
    # handles end-user consent directly; the backend just stores the resulting
    # per-user apiUrl + token and fetches traits/sentiment. Partner API key is
    # only needed for partner-level operations (currently none), left blank
    # so the feature degrades gracefully when not configured.
    onairos_partner_api_key: str = Field(default="", description="Optional Onairos partner API key")
    # Onairos *client* SDK key (the `ona_...` value the mobile SDK initializes with).
    # Served to the app at runtime via GET /api/onairos/config so it is NOT baked
    # into the IPA bundle (where it would be publicly extractable) and can be
    # rotated server-side without an app release.
    onairos_api_key: str = Field(default="", description="Onairos client SDK key served to the app at runtime")
    onairos_http_timeout_seconds: float = Field(
        default=6.0, description="HTTP timeout for Onairos inference calls"
    )
    onairos_traits_ttl_seconds: int = Field(
        default=43200,
        description="How long to trust the cached Onairos trait snapshot before re-fetching (12h default).",
    )

    # External Facial Analysis API (cannon_facial_analysis service)
    facial_analysis_api_url: str = Field(default="http://13.236.183.141:8001/api")
    
    # Google integrations (Calendar / Gmail OAuth + Maps Platform). All
    # default-empty: every Google feature no-ops gracefully until keys land.
    google_client_id: str = Field(default="")
    google_client_secret: str = Field(default="")
    google_redirect_uri: str = Field(
        default="", description="OAuth callback, e.g. https://api.usemaxapp.com/api/google/callback"
    )
    google_maps_api_key: str = Field(default="", description="Places + Distance Matrix (server-side)")
    gmail_scan_enabled: bool = Field(
        default=False,
        description="Gmail commitment scanning (restricted scope - enable only after CASA review)",
    )
    calendar_link_enabled: bool = Field(
        default=True,
        description="Google Calendar link feature (calendar.readonly). Set CALENDAR_LINK_ENABLED=false to hide.",
    )
    # Google Sign-In (identity) client IDs per platform. The web/expo client id
    # is the audience an ID token is minted for; iOS gets its own. Both fall
    # back to google_client_id so a single OAuth client also works.
    google_web_client_id: str = Field(default="")
    google_ios_client_id: str = Field(default="")

    # Stripe -- secret key stays server-side; publishable key is only for reference / admin.
    stripe_secret_key: str = Field(default="")
    stripe_publishable_key: str = Field(default="")
    stripe_webhook_secret: str = Field(default="")
    # Legacy embedded-checkout price (kept for backward compat; not used by native flow)
    stripe_price_id: str = Field(default="")
    stripe_basic_price_id: str = Field(default="")
    stripe_premium_price_id: str = Field(default="")
    subscription_price_monthly: float = Field(default=9.99)
    subscription_currency: str = Field(default="usd")
    # Weekly subscription prices -- create as *recurring / weekly* in Stripe Dashboard
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

    # Web hosted-checkout billing (browser client). OFF by default and inert
    # unless a Stripe secret key is also configured, so this never touches the
    # live Apple-native iOS billing path. See api/payments_web.py.
    stripe_web_billing_enabled: bool = Field(default=False)
    # Absolute base URL of the web app; Stripe success/cancel redirects are
    # built by joining server-validated relative paths onto this (no open
    # redirect). e.g. https://app.usemaxapp.com
    web_app_url: str = Field(default="")
    # Free-trial length for web Stripe checkout (days). 0 disables the trial.
    web_trial_days: int = Field(default=3)

    # Sendblue (iMessage / SMS) -- https://sendblue.com/
    sendblue_api_key_id: str = Field(default="", description="sb-api-key-id header")
    sendblue_api_secret_key: str = Field(default="", description="sb-api-secret-key header")
    sendblue_from_number: str = Field(default="", description="Your Sendblue line E.164, e.g. 16468304204")
    sendblue_webhook_secret: str = Field(
        default="",
        description="Optional: must match Sendblue webhook secret header for /api/sendblue/receive",
    )
    # DEV ONLY: set SMS_SCHEDULER_TEST_FAST_MODE=true -- 1-min scheduler ticks, bypass clock windows so SMS
    # fires immediately; coaching  weekly send at most once per user until you restart the API process.
    sms_scheduler_test_fast_mode: bool = Field(default=False)

    # Whether THIS process runs the APScheduler background jobs (notifications,
    # coaching, calendar polls). Default true = today's single-instance posture.
    # Set RUN_SCHEDULER=false on additional web instances / workers when scaling
    # horizontally — the scheduler is in-process, so two instances running it
    # would double-send every notification.
    run_scheduler: bool = Field(default=True)

    # When true (default), FitMax and HairMax use fixed question scripts in chat.py before schedule creation.
    # When false, those modules use the LangChain agent only (LLM-written replies + tools), like Skinmax/Heightmax.
    chat_scripted_fitmax_hairmax_onboarding: bool = Field(default=True)
    # When true (default), BoneMax uses a deterministic intake flow (workout/TMJ/gum/screen)
    # before schedule creation to avoid off-topic LLM drift and re-ask loops.
    chat_scripted_bonemax_onboarding: bool = Field(default=True)

    # UTC cutoff: accounts created before this see the main-app tour as already completed.
    # Set to the ISO-8601 deploy moment so existing subscribers are not surprised by a tour.
    main_app_tour_cutoff_at: Optional[datetime] = Field(
        default=None,
        description="ISO-8601 UTC datetime; accounts created before this skip the spotlight tour.",
    )

    # Apple Push Notification service (direct HTTP/2) -- .p8 key PEM or base64-of-PEM
    apns_auth_key_p8: str = Field(default="", description="APNs Auth Key PEM or base64-encoded PEM")
    apns_key_id: str = Field(default="", description="10-char Key ID from Apple Developer")
    apns_team_id: str = Field(default="", description="Apple Team ID (iss claim)")
    apns_bundle_id: str = Field(default="com.cannon.mobile", description="apns-topic / bundle id")
    apns_use_sandbox: bool = Field(
        default=False,
        description="True → api.sandbox.push.apple.com (Xcode debug builds only); False → production (TestFlight / App Store)",
    )

    # --- Notifications v2 daily planner (services.notification_planner) ------
    # 4-6/day is a CEILING, not a quota. Min interval keeps pushes from clumping.
    notif_daily_cap: int = Field(default=5, description="Max pushes/day per user (clamped 4-6)")
    notif_min_interval_min: int = Field(default=90, description="Minimum minutes between any two pushes")
    notif_lapse_days: int = Field(default=4, description="No app-open for this many days => lapsed (re-engagement)")
    notif_foreground_suppress_min: int = Field(default=5, description="Suppress pushes if app used within this many minutes")
    notif_broadcast_weekly_cap: int = Field(default=2, description="Global cap on admin broadcasts per rolling week")
    # Adaptive backoff: ignored pushes step a user's frequency DOWN toward 1-2/day.
    notif_backoff_min_delivered: int = Field(default=6, description="Min delivered before low-open backoff kicks in")
    # Kill switch: True pauses ALL outbound pushes instantly (ops lever).
    notif_kill_switch: bool = Field(default=False, description="Pause ALL push sends instantly")

    # Apple In-App Purchase -- App Store Server API v1 (transaction verification)
    apple_app_store_connect_issuer_id: str = Field(default="", description="Issuer ID from App Store Connect → Keys → In-App Purchase")
    apple_app_store_connect_key_id: str = Field(default="", description="Key ID for the In-App Purchase API key")
    apple_app_store_connect_private_key: str = Field(default="", description=".p8 PEM or base64-of-PEM for IAP key")
    apple_bundle_id: str = Field(default="com.cannon.mobile", description="App bundle ID for IAP verification")
    apple_iap_product_id_basic: str = Field(default="com.cannon.mobile.subscribe.basic.weekly")
    apple_iap_product_id_premium: str = Field(default="com.cannon.mobile.subscribe.premium.weekly")
    apple_iap_force_sandbox_api: bool = Field(default=False, description="Try sandbox API first when verifying transactions")
    apple_asn_shared_secret: str = Field(default="", description="Shared secret for App Store Server Notifications V2")
    
    # AWS S3
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    aws_s3_bucket: str = Field(default="cannon-app-uploads")
    aws_s3_region: str = Field(default="us-east-1")
    # Application
    app_name: str = Field(default="Max")
    app_env: str = Field(default="development")
    # Default OFF. When True, the global exception handler returns raw exception
    # text to clients (stack traces, DB schema, file paths) — never in production.
    # Set DEBUG=true explicitly for local development only.
    debug: bool = Field(default=False)
    # SQLAlchemy query echo -- off by default, independent of `debug`. Turning this
    # on in production (Render/Fly/etc.) floods the log pipeline with a full SELECT
    # dump for every single authenticated request, which crushes dashboards and
    # burns log-ingestion quota for no real diagnostic value.
    sql_echo: bool = Field(default=False)
    api_version: str = Field(default="v1")
    
    # CORS -- comma-separated; Expo web uses :8081 (also matched by localhost regex in main.py when not production)
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

        Do NOT append ?pgbouncer=true -- asyncpg doesn't understand that query arg
        and crashes with 'unexpected keyword argument'. PgBouncer-specific
        settings (statement_cache_size=0) are handled in connect_args instead
        (see db/sqlalchemy.py::_supabase_connect_args).
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

    @property
    def is_production(self) -> bool:
        """True in any real deployment. `app_env` alone is unreliable (easy to
        leave at the default), so we also treat the Render/PRODUCTION platform
        env vars as authoritative. Used to hard-disable dev-only endpoints
        (faux signups, dev Google sign-in, test-activate) so they can never mint
        free/paid accounts or bypass the paywall in production."""
        app_env = (self.app_env or "").strip().lower()
        return app_env == "production" or bool(
            os.getenv("RENDER") or os.getenv("PRODUCTION")
        )

    def validate_production_config(self) -> None:
        """Fail fast when critical Supabase DB env vars are missing in production."""
        if not self.is_production:
            return

        errors: list[str] = []
        if (self.supabase_db_host or "").strip().lower() in {"", "localhost", "127.0.0.1"}:
            errors.append("SUPABASE_DB_HOST is not set to a remote Supabase host")
        if not (self.supabase_db_password or "").strip():
            errors.append("SUPABASE_DB_PASSWORD is empty")

        if errors:
            raise RuntimeError(
                "Production database configuration is invalid: "
                + "; ".join(errors)
            )
    
    class Config:
        # Search both repo-root and backend-local .env so WSL / dev / container
        # layouts all work. Files are checked in order; later values override.
        env_file = (
            str(_REPO_ROOT / ".env"),
            str(_BACKEND_DIR / ".env"),
        )
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


_DEFAULT_JWT_SECRET = "change-this-secret-key"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    s = Settings()
    # Refuse to boot in production with the default JWT secret -- that would let
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

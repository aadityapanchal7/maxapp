"""
Max - FastAPI Backend
Main application entry point
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import os
import traceback
import logging

from config import settings
from db import init_db, close_db, init_rds_db, close_rds_db
from api import (
    auth_router, users_router, scans_router, payments_router, payments_web_router,
    courses_router, events_router, forums_router, chat_router, leaderboard_router,
    admin_router, admin_forums_v2_router, notifications_router, admin_notifications_router, schedules_router, maxes_router,
    forums_v2_router,
    sendblue_webhook_router,
    onairos_router,
    personalization_router,
    achievements_router,
    marketplace_router,
    planner_router,
    analytics_router,
    google_router,
    referral_router,
    creator_applications_router,
    creator_social_router,
    user_inbox_router,
    creator_onboarding_router,
    creators_router,
    config_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    settings.validate_production_config()
    await init_db()
    # Idempotently seed built-in free-comp referral codes (e.g. CASH99) so they
    # exist in every environment. Guarded by the flag; never blocks startup.
    if settings.referrals_enabled:
        try:
            from db.sqlalchemy import AsyncSessionLocal
            from services.referral_service import ensure_default_codes
            async with AsyncSessionLocal() as _seed_session:
                await ensure_default_codes(_seed_session)
        except Exception as _seed_err:  # noqa: BLE001
            import logging as _logging
            _logging.getLogger("referral").warning("default comp-code seed skipped: %s", _seed_err)
    from services.prompt_loader import refresh_prompt_cache
    await refresh_prompt_cache()
    await init_rds_db()
    # Warm BM25 RAG indexes so the first KNOWLEDGE turn doesn't pay the
    # cold-load round-trip (~150-300ms). Logged + swallowed on failure.
    from services.rag_service import warm_indexes
    from services.task_catalog_service import warm_catalog
    # Warm in parallel — both are independent disk/DB reads.
    import asyncio as _asyncio
    await _asyncio.gather(warm_indexes(), warm_catalog(), return_exceptions=True)
    # Register DB-backed creator maxes into the catalog (after the .md docs load).
    try:
        from db.sqlalchemy import AsyncSessionLocal as _Session
        from services.creator_service import warm_creator_catalog
        async with _Session() as _cdb:
            await warm_creator_catalog(_cdb)
    except Exception:
        logging_mod = __import__("logging")
        logging_mod.getLogger("creator").warning("creator catalog warm skipped", exc_info=True)
    # Start background scheduler for notifications
    from services.scheduler_job import start_scheduler, stop_scheduler
    from services.apns_service import apns_configured
    import logging
    if not apns_configured():
        logging.getLogger("apns").warning(
            "APNs not configured — push notifications will be silently skipped. "
            "Set APNS_AUTH_KEY_P8, APNS_KEY_ID, APNS_TEAM_ID in .env to enable iOS push."
        )
    # Env-gated so extra instances can run scheduler-free when scaling out
    # (two in-process schedulers would double-send every notification).
    scheduler = start_scheduler(app) if settings.run_scheduler else None
    if scheduler is None and not settings.run_scheduler:
        logging.getLogger("scheduler").info("RUN_SCHEDULER=false — background jobs disabled on this instance")
    yield
    # Shutdown
    stop_scheduler(scheduler)
    await close_db()
    await close_rds_db()


# Create FastAPI app
app = FastAPI(
    title="Max API",
    description="Premium Lookmaxxing App Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Compress JSON responses (reduces payload size on slow links)
app.add_middleware(GZipMiddleware, minimum_size=800)

# CORS: explicit origins from CORS_ORIGINS, plus any http(s) localhost port when not production.
# (Expo web is often :8081; DEBUG=false alone would previously drop the regex and break signup from web.)
_cors_origins = settings.cors_origins_list
_app_env = (getattr(settings, "app_env", "") or "").strip().lower()
# Localhost/LAN origins are allowed ONLY outside production. Do NOT also key this
# on `debug` — a stray DEBUG=true in production must never widen CORS to let a
# local proxy make credentialed cross-origin requests.
# Use the hardened `is_production` flag (the authoritative guard used everywhere
# else) rather than an exact APP_ENV == "production" match: on a real Render
# deploy where APP_ENV is left at its default, an exact match would (wrongly)
# keep the localhost/LAN regex enabled with allow_credentials=True.
_allow_localhost_regex = not settings.is_production
# LAN IPs: Expo web opened as http://192.168.x.x:8081 (phone) must be allowed to call the API.
_cors_regex = (
    (
        r"https?://("
        r"localhost|127\.0\.0\.1|\[::1\]"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r")(:\d)?$"
    )
    if _allow_localhost_regex
    else None
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


class PrivateNetworkAccessMiddleware(BaseHTTPMiddleware):
    """Satisfy Chrome local-network preflight (browser → http://127.0.0.1:8000)."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.method == "OPTIONS":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response


app.add_middleware(PrivateNetworkAccessMiddleware)


_DB_CONN_ERROR_HINTS = (
    "ConnectionDoesNotExist",
    "connection was closed",
    "connection is closed",
    "ConnectionRefused",
    "CannotConnectNow",
    "TooManyConnections",
    "InterfaceError",
    "OperationalError",
    "connection rejected",
    "the database system is",
)


def _looks_like_db_outage(exc: Exception) -> bool:
    """A dropped/unreachable Postgres connection should read as a transient
    503 (try again), not a generic 500 — and never leak the raw SQL."""
    blob = f"{type(exc).__name__}: {exc}"
    return any(hint.lower() in blob.lower() for hint in _DB_CONN_ERROR_HINTS)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return JSON with CORS headers.

    Internal error text (stack traces, raw SQL, asyncpg messages) is NEVER
    returned to clients in production — only when debug is on AND we are not in
    a real deployment. This closes the info-disclosure where a DB outage echoed
    the full failing SQL back to the app."""
    origin = request.headers.get("origin", "*")
    headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
    }
    if settings.debug:
        traceback.print_exc()

    # A database connectivity failure is transient infrastructure, not a client
    # mistake — surface it as 503 so the app can show "try again" and retry.
    if _looks_like_db_outage(exc):
        print(f"[DB][OUTAGE] {type(exc).__name__}: {str(exc)[:200]}")
        return JSONResponse(
            status_code=503,
            content={"detail": "We're having trouble reaching our servers. Please try again in a moment."},
            headers=headers,
        )

    expose = settings.debug and not settings.is_production
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) if expose else "Internal server error"},
        headers=headers,
    )


# Include routers
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(scans_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.include_router(payments_web_router, prefix="/api")
app.include_router(courses_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(forums_router, prefix="/api")
app.include_router(forums_v2_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(leaderboard_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(admin_forums_v2_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(admin_notifications_router, prefix="/api")
app.include_router(schedules_router, prefix="/api")
app.include_router(maxes_router, prefix="/api")
app.include_router(sendblue_webhook_router, prefix="/api")
app.include_router(onairos_router, prefix="/api")
app.include_router(personalization_router, prefix="/api")
app.include_router(achievements_router, prefix="/api")
app.include_router(marketplace_router, prefix="/api")
app.include_router(planner_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(google_router, prefix="/api")
app.include_router(referral_router, prefix="/api")
app.include_router(creator_applications_router, prefix="/api")
app.include_router(creator_social_router, prefix="/api")
app.include_router(user_inbox_router, prefix="/api")
app.include_router(creator_onboarding_router, prefix="/api")
app.include_router(creators_router, prefix="/api")
app.include_router(config_router, prefix="/api")

# Mount uploads directory
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/")
async def root():
    return {"message": "Max API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Liveness + DB readiness probe.

    Returns 200 {status:"healthy"} only when the database is reachable, so a
    load balancer can route away from an instance whose DB connection is dead
    instead of sending it live traffic. DB failure → 503 {status:"degraded"}.
    """
    from fastapi.responses import JSONResponse
    from sqlalchemy import text as _text
    from db.sqlalchemy import engine as _engine

    db_ok = True
    try:
        async with _engine.connect() as conn:
            await conn.execute(_text("SELECT 1"))
    except Exception as e:
        db_ok = False
        logging.getLogger(__name__).warning("health check DB probe failed: %s", e)

    # Liveness, not readiness: always 200 while the process is up so a transient
    # DB blip can't fail a deploy or crash-loop the instance under Render's health
    # check. DB connectivity is reported in the body for observability.
    body = {"status": "healthy" if db_ok else "degraded", "build": "20260715a-single-plan", "db": db_ok}
    return JSONResponse(status_code=200, content=body)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.debug)

"""
Max App - FastAPI Backend
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

from config import settings
from db import init_db, close_db, init_rds_db, close_rds_db
from api import (
    auth_router, users_router, scans_router, payments_router,
    courses_router, events_router, forums_router, chat_router, leaderboard_router,
    admin_router, admin_forums_v2_router, notifications_router, schedules_router, maxes_router,
    forums_v2_router,
    sendblue_webhook_router,
    onairos_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    settings.validate_production_config()
    await init_db()
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
    # Start background scheduler for notifications
    from services.scheduler_job import start_scheduler, stop_scheduler
    from services.apns_service import apns_configured
    import logging
    if not apns_configured():
        logging.getLogger("apns").warning(
            "APNs not configured — push notifications will be silently skipped. "
            "Set APNS_AUTH_KEY_P8, APNS_KEY_ID, APNS_TEAM_ID in .env to enable iOS push."
        )
    scheduler = start_scheduler(app)
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
_allow_localhost_regex = _app_env != "production" or getattr(settings, "debug", False)
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return JSON with CORS headers."""
    origin = request.headers.get("origin", "*")
    if settings.debug:
        traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) if settings.debug else "Internal server error"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        },
    )


# Include routers
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(scans_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.include_router(courses_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(forums_router, prefix="/api")
app.include_router(forums_v2_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(leaderboard_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(admin_forums_v2_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(schedules_router, prefix="/api")
app.include_router(maxes_router, prefix="/api")
app.include_router(sendblue_webhook_router, prefix="/api")
app.include_router(onairos_router, prefix="/api")

# Mount uploads directory
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/")
async def root():
    return {"message": "Max API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "build": "20260412b"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.debug)

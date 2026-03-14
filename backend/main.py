"""
Cannon App - FastAPI Backend
Main application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from config import settings
from db import init_db, close_db, init_rds_db, close_rds_db
from api import (
    auth_router, users_router, scans_router, payments_router,
    courses_router, events_router, forums_router, chat_router, leaderboard_router,
    admin_router, notifications_router
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    await init_db()      # Initialize Supabase tables
    await init_rds_db()  # Initialize RDS tables
    yield
    # Shutdown
    await close_db()     # Close Supabase connection
    await close_rds_db() # Close RDS connection


# Create FastAPI app
app = FastAPI(
    title="Cannon API",
    description="Premium Lookmaxxing App Backend",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(scans_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.include_router(courses_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(forums_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(leaderboard_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")

# Mount uploads directory
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/")
async def root():
    return {"message": "Cannon API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.debug)

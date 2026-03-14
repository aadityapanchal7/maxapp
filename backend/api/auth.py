"""
Authentication API - Login, Signup, Token Management
"""

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import bcrypt
from jose import jwt
from datetime import datetime, timedelta
import hashlib

from config import settings
from db import get_db
from models.user import (
    UserCreate, UserLogin, UserResponse, UserInDB,
    TokenResponse, OnboardingData, UserProfile, TokenRefreshRequest
)
from models.sqlalchemy_models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


def hash_password(password: str) -> str:
    """Hash a password with SHA-256 pre-hashing to support > 72 chars"""
    pre_hash = hashlib.sha256(password.encode()).hexdigest().encode()
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pre_hash, salt)
    return hashed.decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password with SHA-256 pre-hashing"""
    try:
        pre_hash = hashlib.sha256(plain_password.encode()).hexdigest().encode()
        return bcrypt.checkpw(pre_hash, hashed_password.encode())
    except Exception:
        return False


def create_access_token(user_id: str) -> str:
    """Create JWT access token"""
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """Create JWT refresh token"""
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@router.post("/signup", response_model=TokenResponse)
async def signup(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new user account
    """
    # Check if email exists
    result = await db.execute(select(User).where(User.email == user_data.email.lower()))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create user
    new_user = User(
        email=user_data.email.lower(),
        password_hash=hash_password(user_data.password),
        created_at=datetime.utcnow(),
        is_paid=False,
        is_admin=False,
        onboarding=OnboardingData().model_dump(),
        profile=UserProfile(bio=user_data.bio).model_dump() if user_data.bio else UserProfile().model_dump(),
        first_scan_completed=False,
        phone_number=user_data.phone_number
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Send WhatsApp welcome message (non-blocking)
    if user_data.phone_number:
        from services.twilio_service import twilio_service
        import asyncio
        asyncio.create_task(twilio_service.send_welcome(user_data.phone_number, user_data.email))

    # Create tokens
    access_token = create_access_token(str(new_user.id))
    refresh_token = create_refresh_token(str(new_user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """
    Login with email and password (OAuth2 form)
    """
    result = await db.execute(select(User).where(User.email == form_data.username.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/login/json", response_model=TokenResponse)
async def login_json(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Login with JSON body (for mobile app)
    """
    result = await db.execute(select(User).where(User.email == user_data.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Refresh access token using refresh token
    """
    try:
        payload = jwt.decode(
            request.refresh_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        user_id = payload.get("sub")
        token_type = payload.get("type")

        if not user_id or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Verify user exists
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        # Create new tokens
        new_access_token = create_access_token(str(user.id))
        new_refresh_token = create_refresh_token(str(user.id))

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer"
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

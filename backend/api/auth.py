"""
Authentication API - Login, Signup, Token Management
"""

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_db
from middleware import get_current_user
from models.sqlalchemy_models import PasswordResetOTP, User
from models.user import (
    AuthMessageResponse,
    ForgotPasswordSmsConfirm,
    ForgotPasswordSmsRequest,
    OnboardingData,
    TokenRefreshRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserProfile,
    UserResponse,
)
from services.sendblue_service import normalize_phone, phone_lookup_candidates, sendblue_service

logger = logging.getLogger(__name__)

# SMS password reset — tune for abuse vs UX
_PASSWORD_RESET_OTP_TTL_MINUTES = 10
_PASSWORD_RESET_MAX_PER_PHONE_PER_HOUR = 3
_PASSWORD_RESET_MAX_CODE_ATTEMPTS = 5

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s or "")


async def resolve_user_by_login_identifier(db: AsyncSession, raw: str) -> User | None:
    """
    Match login field to email, phone (normalized + lookup variants), or username.
    """
    s = (raw or "").strip()
    if not s:
        return None
    s_lower = s.lower()
    if "@" in s:
        result = await db.execute(select(User).where(User.email == s_lower))
        return result.scalar_one_or_none()
    if len(_digits_only(s)) >= 10:
        normalized = normalize_phone(s)
        candidates = list(dict.fromkeys(phone_lookup_candidates(normalized) + [normalized]))
        result = await db.execute(select(User).where(User.phone_number.in_(candidates)))
        return result.scalar_one_or_none()
    result = await db.execute(select(User).where(User.username == s_lower))
    return result.scalar_one_or_none()


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
        "sub": user_id,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """Create JWT refresh token"""
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode = {
        "sub": user_id,
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
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username exists
    result = await db.execute(select(User).where(User.username == user_data.username.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # One phone number per account (match normalized + common stored variants)
    normalized_phone = normalize_phone(user_data.phone_number.strip())
    phone_candidates = list(
        dict.fromkeys(phone_lookup_candidates(normalized_phone) + [normalized_phone])
    )
    result = await db.execute(select(User).where(User.phone_number.in_(phone_candidates)))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered",
        )

    # Create user record
    user = User(
        email=user_data.email.lower(),
        password_hash=hash_password(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        username=user_data.username.lower(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_paid=False,
        is_admin=False,
        onboarding=OnboardingData().model_dump(),
        profile=UserProfile(bio=user_data.bio).model_dump() if user_data.bio else UserProfile().model_dump(),
        first_scan_completed=False,
        phone_number=normalized_phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user_id = str(user.id)
    
    # Create tokens
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """
    OAuth2 form login: use `username` field for email, username, or phone.
    """
    user = await resolve_user_by_login_identifier(db, form_data.username)

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = str(user.id)
    
    # Create tokens
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/login/json", response_model=TokenResponse)
async def login_json(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Login with JSON — `identifier` (or legacy `email`): email, username, or phone.
    """
    user = await resolve_user_by_login_identifier(db, user_data.identifier)

    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
        )
    user_id = str(user.id)
    
    # Create tokens
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


_GENERIC_RESET_MSG = (
    "If an account exists with that phone number, we sent a text with a reset code. "
    "It expires in a few minutes."
)


@router.post("/forgot-password/sms", response_model=AuthMessageResponse)
async def forgot_password_sms(
    body: ForgotPasswordSmsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a 6-digit code via SMS to the phone on file. Rate-limited per phone.
    Response is always generic (no user enumeration).
    """
    normalized = normalize_phone(body.phone_number.strip())
    phone_candidates = list(dict.fromkeys(phone_lookup_candidates(normalized) + [normalized]))

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    count_result = await db.execute(
        select(func.count())
        .select_from(PasswordResetOTP)
        .where(
            PasswordResetOTP.phone_normalized == normalized,
            PasswordResetOTP.created_at >= since,
        )
    )
    recent = int(count_result.scalar_one() or 0)
    if recent >= _PASSWORD_RESET_MAX_PER_PHONE_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many reset attempts. Try again in an hour.",
        )

    result = await db.execute(select(User).where(User.phone_number.in_(phone_candidates)))
    user = result.scalar_one_or_none()

    if not user or not user.phone_number:
        return AuthMessageResponse(message=_GENERIC_RESET_MSG)

    await db.execute(
        delete(PasswordResetOTP).where(
            PasswordResetOTP.user_id == user.id,
            PasswordResetOTP.consumed_at.is_(None),
        )
    )

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_PASSWORD_RESET_OTP_TTL_MINUTES)
    now = datetime.now(timezone.utc)
    otp_row = PasswordResetOTP(
        user_id=user.id,
        phone_normalized=normalized,
        code_hash=hash_password(code),
        expires_at=expires_at,
        attempts=0,
        consumed_at=None,
        created_at=now,
    )
    db.add(otp_row)
    await db.commit()

    msg = (
        f"max reset code: {code} (expires in {_PASSWORD_RESET_OTP_TTL_MINUTES} min). "
        "ignore this if it wasn't you."
    )
    sent = await sendblue_service.send_sms(user.phone_number, msg)
    if not sent:
        logger.warning("Password reset SMS failed for user_id=%s", user.id)

    return AuthMessageResponse(message=_GENERIC_RESET_MSG)


@router.post("/forgot-password/sms/confirm", response_model=AuthMessageResponse)
async def forgot_password_sms_confirm(
    body: ForgotPasswordSmsConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Verify SMS code and set a new password."""
    normalized = normalize_phone(body.phone_number.strip())
    phone_candidates = list(dict.fromkeys(phone_lookup_candidates(normalized) + [normalized]))

    result = await db.execute(select(User).where(User.phone_number.in_(phone_candidates)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    now = datetime.now(timezone.utc)
    otp_result = await db.execute(
        select(PasswordResetOTP)
        .where(
            PasswordResetOTP.user_id == user.id,
            PasswordResetOTP.consumed_at.is_(None),
            PasswordResetOTP.expires_at > now,
        )
        .order_by(desc(PasswordResetOTP.created_at))
        .limit(1)
    )
    otp_row = otp_result.scalar_one_or_none()
    if not otp_row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    if (otp_row.attempts or 0) >= _PASSWORD_RESET_MAX_CODE_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many incorrect attempts. Request a new code.",
        )

    if not verify_password(body.code, otp_row.code_hash):
        otp_row.attempts = (otp_row.attempts or 0) + 1
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    otp_row.consumed_at = now
    user.password_hash = hash_password(body.new_password)
    user.updated_at = datetime.utcnow()
    await db.commit()

    return AuthMessageResponse(message="Password updated. You can sign in now.")


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
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        result = await db.execute(select(User).where(User.id == user_uuid))
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # Create new tokens
        new_access_token = create_access_token(user_id)
        new_refresh_token = create_refresh_token(user_id)
        
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


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        first_name=current_user.get("first_name"),
        last_name=current_user.get("last_name"),
        username=current_user.get("username"),
        created_at=current_user["created_at"],
        is_paid=current_user.get("is_paid", False),
        subscription_status=current_user.get("subscription_status"),
        subscription_end_date=current_user.get("subscription_end_date"),
        onboarding=OnboardingData(**current_user.get("onboarding", {})),
        profile=UserProfile(**current_user.get("profile", {})),
        first_scan_completed=current_user.get("first_scan_completed", False),
        is_admin=current_user.get("is_admin", False),
        phone_number=current_user.get("phone_number")
    )

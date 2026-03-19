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
from uuid import UUID

from config import settings
from db import get_db
from models.user import (
    UserCreate, UserLogin, UserResponse, UserInDB,
    TokenResponse, OnboardingData, UserProfile, TokenRefreshRequest
)
from models.sqlalchemy_models import User
from middleware import get_current_user

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
        phone_number=user_data.phone_number
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
    Login with email and password
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == form_data.username.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
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
    Login with JSON body (for mobile app)
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == user_data.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
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

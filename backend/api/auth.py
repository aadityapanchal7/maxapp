"""
Authentication API - Login, Signup, Token Management
"""

import hashlib
import logging
import random
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from fastapi import APIRouter, HTTPException, status, Depends, Header
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from sqlalchemy import delete, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_db
from middleware import get_current_user
from middleware.rate_limit import rate_limit
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
    # Try the most-likely match for the shape of the input first, but always
    # fall through to a username lookup so any valid username resolves —
    # even an all-digit one (which would otherwise read as a phone) or one
    # that happens to contain an "@".
    if "@" in s:
        result = await db.execute(select(User).where(User.email == s_lower))
        user = result.scalar_one_or_none()
        if user:
            return user
    if len(_digits_only(s)) >= 10:
        normalized = normalize_phone(s)
        candidates = list(dict.fromkeys(phone_lookup_candidates(normalized) + [normalized]))
        result = await db.execute(select(User).where(User.phone_number.in_(candidates)))
        user = result.scalar_one_or_none()
        if user:
            return user
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


@router.post(
    "/signup",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit(limit=10, window_s=3600, scope="signup"))],
)
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

    # The anon subdomain is reserved for credential-less accounts — a real signup
    # must never land on it (else it'd look "claimable").
    if _is_anonymous_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That email domain is reserved. Please use a different email.",
        )
    
    # Check if username exists
    result = await db.execute(select(User).where(User.username == user_data.username.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    normalized_phone = None
    raw_phone = (user_data.phone_number or "").strip()
    if raw_phone:
        normalized_phone = normalize_phone(raw_phone)
        digits_only = re.sub(r"\D", "", normalized_phone)
        if len(digits_only) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Enter a valid phone number with country code, or leave phone blank.",
            )
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
    try:
        await db.commit()
    except IntegrityError:
        # Double-submitted signup races past the existence checks above; the
        # loser's INSERT violates the unique email/username/phone constraint.
        # Roll back and return the same 400 the pre-check would have.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
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


def _random_string(length: int, chars: str = string.ascii_lowercase + string.digits) -> str:
    return "".join(random.choices(chars, k=length))


def _build_demo_onboarding() -> dict:
    """Shared randomized onboarding payload used by faux-signup variants."""
    unit_system = random.choice(["imperial", "metric"])
    if unit_system == "imperial":
        height = round(random.uniform(60, 76), 1)  # inches
        weight = round(random.uniform(110, 220), 1)  # lbs
        height_cm = round(height * 2.54, 1)
        weight_kg = round(weight * 0.453592, 1)
    else:
        height_cm = round(random.uniform(155, 195), 1)
        weight_kg = round(random.uniform(50, 100), 1)
        height = height_cm
        weight = weight_kg

    priorities = ["face_structure", "skin", "hair", "body", "height"]
    random.shuffle(priorities)
    goals = random.sample(["skinmax", "hairmax", "fitmax", "bonemax", "heightmax"], k=2)

    return {
        "completed": True,
        "questionnaire_v2_completed": True,
        "goals": goals,
        "priority_order": priorities,
        "appearance_concerns": random.sample(
            ["acne", "dark_circles", "jawline", "hair_thinning", "posture", "body_fat", "skin_texture"],
            k=random.randint(1, 3),
        ),
        "age": random.randint(16, 35),
        "gender": random.choice(["male", "female"]),
        "height": height,
        "weight": weight,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "unit_system": unit_system,
        "timezone": "America/New_York",
        "experience_level": random.choice(["beginner", "intermediate"]),
        "activity_level": "moderate",
        "skin_type": random.choice(["oily", "dry", "combination", "normal"]),
        "equipment": random.sample(["dumbbells", "barbell", "pull_up_bar", "none"], k=1),
        "wake_time": "07:00",
        "sleep_time": "23:00",
        "screen_hours_daily": random.choice(["under_4", "4_6", "6_8"]),
        "primary_skin_concern": "none",
        "secondary_skin_concern": "none",
        "skincare_routine_level": random.choice(["none", "basic", "moderate"]),
        "hair_family_history": random.choice(["yes", "no", "unsure"]),
        "hair_current_loss": random.choice(["no", "starting", "yes_active"]),
        "hair_treatments_current": "none",
        "fitmax_primary_goal": random.choice(["muscle_gain", "fat_loss", "recomp"]),
        "fitmax_training_experience": random.choice(["none", "beginner", "intermediate"]),
        "fitmax_equipment": random.choice(["full_gym", "dumbbells", "bodyweight"]),
        "fitmax_workout_days_per_week": random.randint(3, 6),
        "preferred_workout_time": "08:00",
    }


def _block_in_production() -> None:
    """Hard-disable dev-only demo endpoints in any real deployment.

    The faux-signup endpoints are UNAUTHENTICATED and mint accounts directly —
    `/faux-signup-skip` even creates a fully-paid premium user. In production
    that is a complete paywall bypass for anyone who can reach the API, so we
    refuse outright. Returns 404 (not 403) so the routes are indistinguishable
    from non-existent ones to an outside probe."""
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")


def _new_demo_identity(prefix: str = "demo") -> tuple[str, str, str, str]:
    tag = _random_string(10)
    email = f"{prefix}_{tag}@trymax.app"
    username = f"{prefix}_{tag}"
    password = secrets.token_urlsafe(16)
    phone = f"+1555{random.randint(1000000, 9999999)}"
    return email, username, password, phone


# ── Anonymous account (Approach A: account-after-scan) ────────────────────────
# A guest taps "Get started" → mint a credential-less, FREE-tier account so the whole
# auth-gated funnel (onboarding + scan) works with a real user WITHOUT asking for an
# email/password up front. Right before the paywall the user CLAIMS the account
# (sets email + password) via /auth/claim.
#
# Unlike the faux-signup endpoints this is PROD-SAFE — but hardened so it can't become
# the next paywall bypass:
#   - is_paid=False / is_admin=False ALWAYS — an anon account can never be premium.
#   - rate-limited per-IP to stop account-spam / DB bloat.
#   - a reserved app-owned email subdomain + a random password the client never sees,
#     so the account can't be password-logged-into until it is claimed, and /signup
#     refuses the reserved domain. NB: this MUST be a VALID email domain — EmailStr
#     (used by UserResponse) rejects special-use TLDs like .invalid / .test, which
#     would 500 GET /users/me for every anon user.
ANON_EMAIL_DOMAIN = "anon.trymax.app"


def _new_anon_identity() -> tuple[str, str, str]:
    tag = _random_string(16)
    return f"anon_{tag}@{ANON_EMAIL_DOMAIN}", f"anon_{tag}", secrets.token_urlsafe(24)


def _is_anonymous_email(email: str | None) -> bool:
    """True for an unclaimed anon account (its email is on the reserved anon domain)."""
    return bool(email) and email.lower().endswith("@" + ANON_EMAIL_DOMAIN)


@router.post(
    "/anon",
    response_model=TokenResponse,
    # Raised from 30/hr: this mints the account behind EVERY "Get started" tap,
    # so a per-IP cap this low locks a whole shared-IP cohort (carrier-grade
    # NAT — campus/corporate wifi, T-Mobile) out of onboarding for a full hour
    # once >30 new installs land behind the same IP — i.e. it blocks the
    # funnel at launch scale. Still capped, just not at a level real cohorts
    # blow through immediately.
    dependencies=[Depends(rate_limit(limit=300, window_s=3600, scope="anon"))],
)
async def anon_signup(db: AsyncSession = Depends(get_db)):
    """Mint a credential-less FREE-tier account so the funnel can run before sign-up.
    Claimed (email + password set) via /auth/claim before checkout."""
    email, username, password = _new_anon_identity()
    user = User(
        email=email,
        password_hash=hash_password(password),  # random — never returned to the client
        first_name="",
        last_name="",
        username=username,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_paid=False,   # SECURITY: anon accounts are NEVER premium
        is_admin=False,
        onboarding={},   # fresh — they go through onboarding
        profile=UserProfile().model_dump(),
        first_scan_completed=False,
        phone_number=None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        token_type="bearer",
    )


@router.post(
    "/claim",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit(limit=10, window_s=3600, scope="claim"))],
)
async def claim_account(
    user_data: UserCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Claim an anonymous account: set its real email + password + username + name.
    Only an UNCLAIMED (anon-email) account can be claimed, so a claim can never
    hijack or overwrite a credentialed user. Never grants premium."""
    result = await db.execute(select(User).where(User.id == UUID(current_user["id"])))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if not _is_anonymous_email(user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account is already set up. Sign in instead.",
        )

    new_email = user_data.email.lower()
    new_username = user_data.username.lower()
    # Uniqueness — against every OTHER user (exclude self).
    if (await db.execute(
        select(User).where(User.email == new_email, User.id != user.id)
    )).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    if (await db.execute(
        select(User).where(User.username == new_username, User.id != user.id)
    )).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")

    normalized_phone = None
    raw_phone = (user_data.phone_number or "").strip()
    if raw_phone:
        normalized_phone = normalize_phone(raw_phone)
        if len(re.sub(r"\D", "", normalized_phone)) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Enter a valid phone number with country code, or leave phone blank.",
            )
        phone_candidates = list(dict.fromkeys(phone_lookup_candidates(normalized_phone) + [normalized_phone]))
        if (await db.execute(
            select(User).where(User.phone_number.in_(phone_candidates), User.id != user.id)
        )).scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already registered")

    user.email = new_email
    user.password_hash = hash_password(user_data.password)
    user.username = new_username
    user.first_name = user_data.first_name
    user.last_name = user_data.last_name
    if user_data.bio:
        prof = dict(user.profile or {})
        prof["bio"] = user_data.bio
        user.profile = prof  # reassign so the JSON column updates
    if normalized_phone:
        user.phone_number = normalized_phone
    user.updated_at = datetime.utcnow()
    # SECURITY: is_paid is intentionally never touched here — claiming ≠ paying.
    await db.commit()
    await db.refresh(user)
    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        token_type="bearer",
    )


@router.post("/faux-signup", response_model=TokenResponse)
async def faux_signup(db: AsyncSession = Depends(get_db)):
    """
    Create a throwaway demo account with pre-completed onboarding so the user
    lands directly on FeaturesIntro → FaceScan.  No real PII required.
    """
    _block_in_production()
    email, username, password, phone = _new_demo_identity("demo")

    user = User(
        email=email,
        password_hash=hash_password(password),
        first_name="Demo",
        last_name="User",
        username=username,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_paid=False,
        is_admin=False,
        onboarding=_build_demo_onboarding(),
        profile=UserProfile().model_dump(),
        first_scan_completed=False,
        phone_number=phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    user_id = str(user.id)
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/faux-signup-fresh", response_model=TokenResponse)
async def faux_signup_fresh(db: AsyncSession = Depends(get_db)):
    """
    Create a throwaway demo account with EMPTY onboarding so the user
    lands on the very first onboarding question. Useful for replaying
    the onboarding flow end-to-end without polluting Auth Connect /
    Apple Sign-In identity. The other faux-signup variants pre-fill
    onboarding so they skip past it.
    """
    _block_in_production()
    email, username, password, phone = _new_demo_identity("fresh")

    user = User(
        email=email,
        password_hash=hash_password(password),
        first_name="Demo",
        last_name="User",
        username=username,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_paid=False,
        is_admin=False,
        onboarding={},   # fresh — no `completed` flag, no answers
        profile=UserProfile().model_dump(),
        first_scan_completed=False,
        phone_number=phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    user_id = str(user.id)
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/faux-signup-skip", response_model=TokenResponse)
async def faux_signup_skip(db: AsyncSession = Depends(get_db)):
    """
    Create a throwaway demo account that is fully provisioned (paid +
    onboarding done + post-subscription steps done) so the client lands
    directly on the Main/home tab, skipping auth, onboarding, scan, and payment.
    """
    _block_in_production()
    email, username, password, phone = _new_demo_identity("skip")

    onboarding_data = _build_demo_onboarding()
    # IMPORTANT: `post_subscription_onboarding=True` means "user is mid-flow,
    # needs to finish the post-pay onboarding". HomeScreen redirects to
    # FaceScanResults when it sees that flag truthy. For "skip → land on home",
    # we want the flag FALSE (= no pending onboarding work).
    # The remaining sub-gates are still set to True so any defensive check
    # downstream sees them done.
    onboarding_data["post_subscription_onboarding"] = False
    onboarding_data["sendblue_connect_completed"] = True
    onboarding_data["notification_channels_completed"] = True
    onboarding_data["module_select_completed"] = True
    onboarding_data["main_app_tour_completed"] = True

    user = User(
        email=email,
        password_hash=hash_password(password),
        first_name="Demo",
        last_name="User",
        username=username,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_paid=True,
        is_admin=False,
        subscription_tier="premium",
        subscription_status="active",
        subscription_end_date=datetime.now(timezone.utc) + timedelta(days=365),
        onboarding=onboarding_data,
        profile=UserProfile().model_dump(),
        first_scan_completed=True,
        phone_number=phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    user_id = str(user.id)
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/dev/toggle-admin")
async def dev_toggle_admin(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DEV-ONLY: flip the CURRENT account's is_admin so you can jump into the
    admin view as the same user you're testing with (and back), without logging
    into a separate admin account. is_admin is read from the DB each request
    (see middleware.auth_middleware) so no re-issued token is needed — the client
    just re-fetches /auth/me and the navigator swaps to AdminNavigator. 404 in
    production (an admin-grant endpoint must never be reachable there)."""
    _block_in_production()
    uid = current_user.get("id") or current_user.get("user_id") or current_user.get("sub")
    user = (await db.execute(select(User).where(User.id == uid))).scalars().first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_admin = not bool(user.is_admin)
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"is_admin": user.is_admin}


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit(limit=10, window_s=300, scope="login"))],
)
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


@router.post(
    "/login/json",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit(limit=10, window_s=300, scope="login"))],
)
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


# ---------------------------------------------------------------------------
# Google Sign-In (identity)
# ---------------------------------------------------------------------------

async def _unique_username(db: AsyncSession, base: str) -> str:
    """A unique, login-safe username derived from an email/name."""
    stem = re.sub(r"[^a-z0-9]", "", (base or "user").lower())[:18] or "user"
    candidate = stem
    for _ in range(8):
        exists = (await db.execute(
            select(User.id).where(User.username == candidate)
        )).first()
        if not exists:
            return candidate
        candidate = f"{stem}{secrets.randbelow(9000) + 1000}"
    return f"{stem}{secrets.token_hex(4)}"


async def _optional_anon_caller(authorization: str | None, db: AsyncSession) -> "User | None":
    """If the request carries a valid access token for an UNCLAIMED anon account,
    return that user — so a social sign-in can CLAIM it (preserving the funnel's
    onboarding + scan) instead of starting a fresh account. Any problem -> None,
    so a bad/expired token never blocks a normal sign-in."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            return None
        user = (await db.execute(
            select(User).where(User.id == UUID(str(payload.get("sub"))))
        )).scalar_one_or_none()
        if user and _is_anonymous_email(user.email):
            return user
    except Exception:  # noqa: BLE001 — best-effort; never block sign-in on a bad token
        return None
    return None


async def _find_or_create_google_user(
    db: AsyncSession,
    *,
    sub: str,
    email: str,
    given_name: str = "",
    family_name: str = "",
    claim_user: "User | None" = None,
) -> tuple[User, bool]:
    """Resolve a Google identity to an app user (created = was new).

    Match order: google_sub (the stable account id) -> email (link an
    existing password account to Google). New users are created with an
    unusable random password and EMPTY onboarding so they run the funnel,
    exactly like a fresh email signup."""
    email = (email or "").strip().lower()

    user = (await db.execute(
        select(User).where(User.google_sub == sub)
    )).scalar_one_or_none()
    if user:
        return user, False

    if email:
        user = (await db.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()
        if user:
            # Link Google to the existing account (same person, same email).
            if not user.google_sub:
                user.google_sub = sub
            if not user.auth_provider or user.auth_provider == "password":
                user.auth_provider = "google"
            user.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(user)
            return user, False

    # Account-after-scan: claim the CALLER's own unclaimed anon account with this
    # Google identity, preserving its onboarding + scan, instead of starting fresh.
    if claim_user is not None and email:
        claim_user.email = email
        claim_user.google_sub = sub
        claim_user.auth_provider = "google"
        if given_name:
            claim_user.first_name = given_name.strip()
        if family_name:
            claim_user.last_name = family_name.strip()
        claim_user.username = await _unique_username(db, email.split("@", 1)[0])
        claim_user.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(claim_user)
        return claim_user, False

    username = await _unique_username(db, email.split("@", 1)[0] if email else "max")
    user = User(
        email=email or f"google_{sub[:12]}@placeholder.max",
        password_hash=hash_password(secrets.token_urlsafe(32)),  # unusable
        first_name=(given_name or "").strip() or "Max",
        last_name=(family_name or "").strip() or "User",
        username=username,
        google_sub=sub,
        auth_provider="google",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_paid=False,
        is_admin=False,
        onboarding={},  # fresh -> runs onboarding, same as faux-signup-fresh
        profile=UserProfile().model_dump(),
        first_scan_completed=False,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Double-tapped "Sign in with Google" for a brand-new user: both requests
        # pass the google_sub/email checks and both INSERT. Roll back and return
        # the winner (idempotent) instead of 500ing.
        await db.rollback()
        existing = (await db.execute(
            select(User).where(User.google_sub == sub)
        )).scalar_one_or_none()
        if existing is None and email:
            existing = (await db.execute(
                select(User).where(User.email == email)
            )).scalar_one_or_none()
        if existing is not None:
            return existing, False
        raise
    await db.refresh(user)
    return user, True


async def _find_or_create_apple_user(
    db: AsyncSession,
    *,
    sub: str,
    email: str,
    given_name: str = "",
    family_name: str = "",
    claim_user: "User | None" = None,
) -> tuple[User, bool]:
    """Resolve an Apple identity to an app user (created = was new).

    Match order: apple_sub (stable) -> email (link an existing account). Apple
    only returns email on the FIRST authorization and name never comes in the
    token (the client passes it once), so apple_sub is the durable key. Mirrors
    the Google helper exactly."""
    email = (email or "").strip().lower()

    user = (await db.execute(
        select(User).where(User.apple_sub == sub)
    )).scalar_one_or_none()
    if user:
        return user, False

    if email:
        user = (await db.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()
        if user:
            if not user.apple_sub:
                user.apple_sub = sub
            if not user.auth_provider or user.auth_provider == "password":
                user.auth_provider = "apple"
            user.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(user)
            return user, False

    # Account-after-scan: claim the caller's own unclaimed anon account.
    if claim_user is not None:
        if email:
            claim_user.email = email
        claim_user.apple_sub = sub
        claim_user.auth_provider = "apple"
        if given_name:
            claim_user.first_name = given_name.strip()
        if family_name:
            claim_user.last_name = family_name.strip()
        claim_user.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(claim_user)
        return claim_user, False

    username = await _unique_username(db, email.split("@", 1)[0] if email else "max")
    user = User(
        email=email or f"apple_{sub[:12]}@placeholder.max",
        password_hash=hash_password(secrets.token_urlsafe(32)),  # unusable
        first_name=(given_name or "").strip() or "Max",
        last_name=(family_name or "").strip() or "User",
        username=username,
        apple_sub=sub,
        auth_provider="apple",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_paid=False,
        is_admin=False,
        onboarding={},  # fresh -> runs onboarding
        profile=UserProfile().model_dump(),
        first_scan_completed=False,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (await db.execute(
            select(User).where(User.apple_sub == sub)
        )).scalar_one_or_none()
        if existing is None and email:
            existing = (await db.execute(
                select(User).where(User.email == email)
            )).scalar_one_or_none()
        if existing is not None:
            return existing, False
        raise
    await db.refresh(user)
    return user, True


@router.post("/apple", response_model=TokenResponse)
async def apple_signin(payload: dict, db: AsyncSession = Depends(get_db), authorization: str | None = Header(default=None)):
    """Sign in / sign up with a Sign in with Apple identity token. The iOS
    client obtains it via AppleAuthentication and POSTs it here (with the name
    on first sign-in only, since Apple provides it once); we verify it against
    Apple's keys, then find-or-create the account and issue our own tokens.
    Required for App Store guideline 4.8 (Google Sign-In needs an equivalent)."""
    from services.apple_signin import apple_signin_available, verify_apple_id_token

    if not apple_signin_available():
        raise HTTPException(status_code=503, detail="Sign in with Apple is not configured")
    token = payload.get("identity_token") or payload.get("id_token")
    if not token:
        raise HTTPException(status_code=422, detail="identity_token required")
    try:
        claims = await verify_apple_id_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    user, _created = await _find_or_create_apple_user(
        db,
        sub=str(claims["sub"]),
        email=str(claims.get("email") or payload.get("email") or ""),
        given_name=str(payload.get("given_name") or ""),
        family_name=str(payload.get("family_name") or ""),
        claim_user=await _optional_anon_caller(authorization, db),
    )
    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        token_type="bearer",
    )


@router.get("/google/config")
async def google_signin_config():
    """What the client needs to start Google Sign-In (and whether it's set
    up at all). Client IDs are public by design."""
    from services.google_integration import google_signin_available
    return {
        "available": google_signin_available(),
        "web_client_id": settings.google_web_client_id or settings.google_client_id,
        "ios_client_id": settings.google_ios_client_id or settings.google_client_id,
    }


@router.post("/google", response_model=TokenResponse)
async def google_signin(payload: dict, db: AsyncSession = Depends(get_db), authorization: str | None = Header(default=None)):
    """Sign in / sign up with a Google ID token. The client obtains the token
    via the Google consent flow and POSTs it here; we verify it against
    Google's keys, then find-or-create the account and issue our own tokens."""
    from services.google_integration import google_signin_available, verify_google_id_token

    if not google_signin_available():
        raise HTTPException(status_code=503, detail="Google Sign-In is not configured")
    token = payload.get("id_token") or payload.get("credential")
    if not token:
        raise HTTPException(status_code=422, detail="id_token required")
    try:
        claims = await verify_google_id_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    if not claims.get("email_verified", False):
        raise HTTPException(status_code=401, detail="Google email is not verified")

    user, _created = await _find_or_create_google_user(
        db,
        sub=str(claims["sub"]),
        email=str(claims.get("email") or ""),
        given_name=str(claims.get("given_name") or ""),
        family_name=str(claims.get("family_name") or ""),
        claim_user=await _optional_anon_caller(authorization, db),
    )
    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        token_type="bearer",
    )


@router.post("/google/dev", response_model=TokenResponse)
async def google_signin_dev(payload: dict, db: AsyncSession = Depends(get_db), authorization: str | None = Header(default=None)):
    """DEV-ONLY: exercise the exact find-or-create + token path WITHOUT a real
    Google token, so the identity flow is testable before OAuth client IDs are
    provisioned. Disabled in production."""
    _block_in_production()  # parity with faux-signup endpoints (P0-7)
    email = str(payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="email required")
    sub = "devgoogle:" + hashlib.sha256(email.encode()).hexdigest()[:24]
    name = str(payload.get("name") or "").strip()
    given, _, family = name.partition(" ")
    user, _created = await _find_or_create_google_user(
        db, sub=sub, email=email, given_name=given, family_name=family,
        claim_user=await _optional_anon_caller(authorization, db),
    )
    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        token_type="bearer",
    )


_GENERIC_RESET_MSG = (
    "If an account exists with that phone number, we sent a text with a reset code. "
    "It expires in a few minutes."
)


@router.post(
    "/forgot-password/sms",
    response_model=AuthMessageResponse,
    dependencies=[Depends(rate_limit(limit=5, window_s=3600, scope="forgot_sms"))],
)
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


@router.post(
    "/forgot-password/sms/confirm",
    response_model=AuthMessageResponse,
    dependencies=[Depends(rate_limit(limit=10, window_s=900, scope="forgot_sms_confirm"))],
)
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
    ob_raw = dict(current_user.get("onboarding") or {})
    if not ob_raw.get("main_app_tour_completed"):
        cutoff = settings.main_app_tour_cutoff_at
        created = current_user.get("created_at")
        if cutoff and created:
            c = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            co = cutoff if cutoff.tzinfo else cutoff.replace(tzinfo=timezone.utc)
            if c < co:
                ob_raw["main_app_tour_completed"] = True

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
        onboarding=OnboardingData(**ob_raw),
        profile=UserProfile(**current_user.get("profile", {})),
        first_scan_completed=current_user.get("first_scan_completed", False),
        is_admin=current_user.get("is_admin", False),
        is_scan_user=current_user.get("is_scan_user", False),
        phone_number=current_user.get("phone_number"),
        subscription_tier=current_user.get("subscription_tier"),
        last_username_change=current_user.get("last_username_change"),
        has_apns_token=current_user.get("has_apns_token", False),
        coaching_tone=current_user.get("coaching_tone") or "default",
        auth_provider=current_user.get("auth_provider") or "password",
    )

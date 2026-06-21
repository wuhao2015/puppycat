from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.deps import UnauthorizedError, get_current_user
from app.errors import PuppycatError
from app.models import User
from app.schemas import (
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegistrationError(PuppycatError):
    status_code = 400


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email or "",
        display_name=user.display_name,
        passport_countries=list(user.passport_countries or []),
        home_country=user.home_country,
    )


def _token_response(user: User) -> TokenResponse:
    settings = get_settings()
    token = create_access_token(user.id, settings)
    return TokenResponse(access_token=token, user=_user_out(user))


@router.post("/register", response_model=TokenResponse)
async def register(
    req: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    settings = get_settings()
    if req.signup_code != settings.signup_code:
        raise RegistrationError("Invalid signup code.")

    email = _normalize_email(req.email)
    if "@" not in email:
        raise RegistrationError("A valid email address is required.")

    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise RegistrationError("An account with that email already exists.")

    user = User(
        email=email,
        display_name=req.display_name or None,
        password_hash=hash_password(req.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    email = _normalize_email(req.email)
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not user.password_hash or not verify_password(req.password, user.password_hash):
        raise UnauthorizedError("Incorrect email or password.")
    return _token_response(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)


@router.patch("/profile", response_model=UserOut)
async def update_profile(
    req: ProfileUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    if req.display_name is not None:
        user.display_name = req.display_name.strip() or None
    if req.passport_countries is not None:
        # Normalise to upper-case ISO-ish codes, de-duplicated, order preserved.
        seen: list[str] = []
        for code in req.passport_countries:
            c = code.strip().upper()
            if c and c not in seen:
                seen.append(c)
        user.passport_countries = seen
    if req.home_country is not None:
        user.home_country = req.home_country.strip().upper() or None
    await session.commit()
    await session.refresh(user)
    return _user_out(user)

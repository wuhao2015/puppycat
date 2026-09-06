from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    register_user,
)
from app.db import get_session
from app.models import User
from app.schemas import (
    AuthResponse,
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    UserResponse,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    user = await register_user(
        session,
        email=str(request.email),
        password=request.password,
        display_name=request.display_name,
        signup_code=request.signup_code,
    )
    return AuthResponse(access_token=create_access_token(user.id), user=user)


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    user = await authenticate_user(
        session,
        email=str(request.email),
        password=request.password,
    )
    return AuthResponse(access_token=create_access_token(user.id), user=user)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    request: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    if "display_name" in request.model_fields_set:
        current_user.display_name = request.display_name
    if request.passport_countries is not None:
        current_user.passport_countries = request.passport_countries

    await session.commit()
    await session.refresh(current_user)
    return current_user

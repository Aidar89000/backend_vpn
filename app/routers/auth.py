from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt

from app.database import get_db
from app.schemas.user import (
    UserCreate,
    UserResponse,
    Token,
    LoginRequest,
    Message,
    UserUpdate,
)
from app.crud.user import (
    create_user,
    get_user_by_username,
    get_user_by_email,
    authenticate_user,
    update_user as update_user_crud,
)
from app.config import get_settings
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["authentication"])
settings = get_settings()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    """Register a new user."""
    # Check if user already exists
    existing_user = await get_user_by_username(db, user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    existing_email = await get_user_by_email(db, user_data.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    db_user = await create_user(db, user_data)
    return db_user


@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Login and get access token."""
    user = await authenticate_user(db, login_data.username, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: Annotated[UserResponse, Depends(get_current_user)]):
    """Get current user info."""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_me(
    user_update: UserUpdate,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update current user info."""
    # Check if new username is taken
    if user_update.username and user_update.username != current_user.username:
        existing = await get_user_by_username(db, user_update.username)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

    # Check if new email is taken
    if user_update.email and user_update.email != current_user.email:
        existing = await get_user_by_email(db, user_update.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already taken",
            )

    db_user = await get_user_by_username(db, current_user.username)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    updated_user = await update_user_crud(db, db_user, user_update)
    return updated_user


@router.post("/logout", response_model=Message)
async def logout(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
):
    """Logout current user."""
    return {"message": "Successfully logged out"}

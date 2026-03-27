from typing import Optional
"""
Auth endpoints: login, refresh, logout, me.
Cookie name: detour_ai_refresh
"""
import os
import uuid
import asyncio

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, field_validator

from utils.auth import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from utils.auth_db import (
    delete_all_refresh_tokens_for_user,
    delete_refresh_token,
    get_user_by_username,
    store_refresh_token,
    update_password,
    validate_and_rotate_refresh_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "detour_ai_refresh"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
REFRESH_TOKEN_TTL_DAYS = 7


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
        max_age=REFRESH_TOKEN_TTL_DAYS * 86400,
        path="/api/auth",
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response) -> TokenResponse:
    user = await asyncio.to_thread(get_user_by_username, body.username)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige Anmeldedaten",
        )

    access_token = create_access_token(user["id"], user["username"], bool(user["is_admin"]))
    raw_refresh = str(uuid.uuid4())
    await asyncio.to_thread(store_refresh_token, user["id"], raw_refresh, REFRESH_TOKEN_TTL_DAYS)
    _set_refresh_cookie(response, raw_refresh)

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    detour_ai_refresh: Optional[str] = Cookie(default=None),
) -> TokenResponse:
    if detour_ai_refresh is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kein Refresh-Token")

    user_id = await asyncio.to_thread(validate_and_rotate_refresh_token, detour_ai_refresh)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges oder abgelaufenes Refresh-Token")

    from utils.auth_db import get_user_by_id
    user = await asyncio.to_thread(get_user_by_id, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzer nicht gefunden")

    access_token = create_access_token(user["id"], user["username"], bool(user["is_admin"]))
    raw_refresh = str(uuid.uuid4())
    await asyncio.to_thread(store_refresh_token, user["id"], raw_refresh, REFRESH_TOKEN_TTL_DAYS)
    _set_refresh_cookie(response, raw_refresh)

    return TokenResponse(access_token=access_token)


@router.post("/logout")
async def logout(
    response: Response,
    detour_ai_refresh: Optional[str] = Cookie(default=None),
) -> dict:
    if detour_ai_refresh:
        await asyncio.to_thread(delete_refresh_token, detour_ai_refresh)
    response.delete_cookie(key=COOKIE_NAME, path="/api/auth")
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=current_user.id, username=current_user.username, is_admin=current_user.is_admin)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    user = await asyncio.to_thread(get_user_by_username, current_user.username)
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Aktuelles Passwort ist falsch")
    new_hash = hash_password(body.new_password)
    await asyncio.to_thread(update_password, current_user.id, new_hash)
    await asyncio.to_thread(delete_all_refresh_tokens_for_user, current_user.id)
    return {"ok": True}

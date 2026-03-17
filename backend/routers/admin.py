"""
Admin-only endpoints: user management.
All routes require is_admin = True.
"""
import asyncio

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, field_validator

from utils.auth import CurrentUser, hash_password, require_admin
from utils.auth_db import (
    create_user,
    delete_user,
    get_user_by_id,
    list_users,
    update_password,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v

    @field_validator("username")
    @classmethod
    def username_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Benutzername darf nicht leer sein")
        return v.strip()


class PasswordResetRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v


@router.get("/users")
async def list_all_users(admin: CurrentUser = Depends(require_admin)) -> dict:
    users = await asyncio.to_thread(list_users)
    return {"users": users}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_new_user(
    body: CreateUserRequest,
    admin: CurrentUser = Depends(require_admin),
) -> dict:
    hashed = hash_password(body.password)
    try:
        user_id = await asyncio.to_thread(create_user, body.username, hashed, body.is_admin)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Benutzername '{body.username}' ist bereits vergeben",
        )
    return {"id": user_id, "username": body.username}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_user(
    user_id: int,
    admin: CurrentUser = Depends(require_admin),
) -> None:
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Eigenes Konto kann nicht gelöscht werden",
        )
    deleted = await asyncio.to_thread(delete_user, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")


@router.patch("/users/{user_id}/password")
async def reset_user_password(
    user_id: int,
    body: PasswordResetRequest,
    admin: CurrentUser = Depends(require_admin),
) -> dict:
    user = await asyncio.to_thread(get_user_by_id, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")
    new_hash = hash_password(body.password)
    await asyncio.to_thread(update_password, user_id, new_hash)
    return {"ok": True}

"""
JWT creation/validation, Argon2id password hashing, FastAPI auth dependencies.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = 15

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


import logging as _logging
_log = _logging.getLogger(__name__)


def verify_jwt_secret() -> None:
    """Call at startup — log a warning and refuse to start if JWT_SECRET is weak or missing."""
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        msg = (
            "JWT_SECRET must be set and at least 32 characters long. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
        _log.warning(msg)
        raise RuntimeError(msg)


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

class TokenPayload(BaseModel):
    sub: int       # user_id
    username: str
    is_admin: bool


def create_access_token(user_id: int, username: str, is_admin: bool) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[TokenPayload]:
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenPayload(sub=int(data["sub"]), username=data["username"], is_admin=data["is_admin"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── FastAPI dependencies ───────────────────────────────────────────────────────

class CurrentUser(BaseModel):
    id: int
    username: str
    is_admin: bool


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder abgelaufenes Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(id=payload.sub, username=payload.username, is_admin=payload.is_admin)


async def get_current_user_sse(request: "Request", token: Optional[str] = None) -> CurrentUser:
    """Like get_current_user but also accepts ?token= query param (needed for EventSource)."""
    from fastapi import Request as _Request
    raw_token = token
    if raw_token is None:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            raw_token = auth_header[7:]
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder abgelaufenes Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(raw_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder abgelaufenes Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(id=payload.sub, username=payload.username, is_admin=payload.is_admin)


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kein Zugriff")
    return user

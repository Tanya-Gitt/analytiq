"""
JWT authentication for the platform.

Uses python-jose for JWT encode/decode. Tokens are issued at login and
contain org_id in the payload. Supabase GoTrue issues its own JWTs with
the same JWT_SECRET — this module validates both.

Token payload shape:
    {
        "sub": "<user_id>",
        "org_id": "<uuid>",
        "exp": <unix_timestamp>,
        "iat": <unix_timestamp>
    }
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError, jwt

_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def _get_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    return secret


def create_access_token(user_id: str, org_id: str) -> str:
    """Issue a signed JWT for a user/org pair."""
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "org_id": org_id,
        "iat": now,
        "exp": now + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)


def verify_jwt_get_org_id(token: str) -> UUID:
    """
    Decode and validate a JWT. Returns the org_id UUID.
    Raises HTTP 401 on any validation failure.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[_ALGORITHM])
    except JWTError:
        raise credentials_exception

    org_id_str: str | None = payload.get("org_id")
    if not org_id_str:
        raise credentials_exception

    try:
        return UUID(org_id_str)
    except ValueError:
        raise credentials_exception

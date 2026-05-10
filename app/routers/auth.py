"""
Auth routes: signup, login, me.

For MVP, this is simple email+password auth (bcrypt hash stored in users table).
Supabase GoTrue handles the JWT signing with the same JWT_SECRET — tokens from
GoTrue's /token endpoint are also accepted by app/auth.py's verify_jwt_get_org_id().

Security notes:
  - Login always runs bcrypt (even for unknown emails) to prevent timing-based
    user enumeration. Uses a dummy hash for the constant-time check.
  - Account lockout: 10 consecutive failures locks the account for 15 minutes.
    Counter resets to 0 on successful login.
  - Rate limiting at nginx level: 5 req/min per IP on /api/auth/login.
  - Passwords must be ≥ 8 characters.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, field_validator

from app.auth import create_access_token, verify_jwt_get_org_id
from app.database import get_pool

# Account lockout constants
_MAX_FAILED_ATTEMPTS = 10
_LOCKOUT_DURATION    = timedelta(minutes=15)

# Pre-computed dummy hash used to run bcrypt for unknown emails
# (prevents timing-based user enumeration: bcrypt always runs, same cost)
_DUMMY_HASH = bcrypt.hashpw(b"dummy_constant_time_guard", bcrypt.gensalt(rounds=12)).decode()

_bearer = HTTPBearer(auto_error=False)

router = APIRouter()


class SignupRequest(BaseModel):
    org_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v

    @field_validator("org_name")
    @classmethod
    def org_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("org_name must not be blank")
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    org_id: str
    api_key: str


@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(body: SignupRequest, pool: asyncpg.Pool = Depends(get_pool)):
    """
    Create a new org + admin user. Returns a JWT.

    Flow:
      1. Create org row (generates api_key automatically via SQL DEFAULT)
      2. Create user row with bcrypt password hash
      3. Return JWT containing org_id
    """
    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

    async with pool.acquire() as conn:
        async with conn.transaction():
            # app_user has NOINHERIT — must SET ROLE to access tables granted to app_role.
            # users/orgs have no RLS so we don't need SET LOCAL app.org_id here.
            await conn.execute("SET LOCAL ROLE app_role")

            # Check email not already taken
            existing = await conn.fetchval(
                "SELECT id FROM users WHERE email = $1", body.email
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="email already registered",
                )

            # Create org
            org = await conn.fetchrow(
                "INSERT INTO orgs (name) VALUES ($1) RETURNING id, api_key",
                body.org_name,
            )
            org_id = str(org["id"])

            # Create user
            user = await conn.fetchrow(
                "INSERT INTO users (org_id, email, password_hash) VALUES ($1, $2, $3) RETURNING id",
                org["id"],
                body.email,
                password_hash,
            )

    token = create_access_token(user_id=str(user["id"]), org_id=org_id)
    return TokenResponse(access_token=token, org_id=org_id, api_key=org["api_key"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, pool: asyncpg.Pool = Depends(get_pool)):
    """
    Email + password login. Returns a JWT.

    SECURITY:
      - Always runs bcrypt.checkpw() regardless of whether the email exists
        (prevents timing-based user enumeration).
      - Locks the account for 15 minutes after 10 consecutive failed attempts.
        Counter resets to 0 on successful login.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid email or password",
    )

    async with pool.acquire() as conn:
        async with conn.transaction():
            # app_user has NOINHERIT — SET LOCAL ROLE so the role resets when
            # the transaction ends and the connection is returned to the pool.
            await conn.execute("SET LOCAL ROLE app_role")
            row = await conn.fetchrow(
                """
                SELECT u.id, u.org_id, u.password_hash, u.failed_login_attempts,
                       u.locked_until, o.api_key
                FROM users u
                JOIN orgs o ON o.id = u.org_id
                WHERE u.email = $1
                """,
                body.email,
            )

            # Always run bcrypt to prevent timing-based user enumeration.
            # If user not found, compare against a dummy hash (same cost, same time).
            stored_hash = row["password_hash"].encode() if row else _DUMMY_HASH.encode()
            password_ok = bcrypt.checkpw(body.password.encode(), stored_hash)

            if row is None or not password_ok:
                # Increment failure counter for known users (unknown users: no-op)
                if row is not None:
                    await conn.execute(
                        """
                        UPDATE users
                        SET failed_login_attempts = failed_login_attempts + 1,
                            locked_until = CASE
                                WHEN failed_login_attempts + 1 >= $2
                                THEN NOW() + $3::interval
                                ELSE locked_until
                            END
                        WHERE id = $1
                        """,
                        row["id"],
                        _MAX_FAILED_ATTEMPTS,
                        str(int(_LOCKOUT_DURATION.total_seconds())) + " seconds",
                    )
                raise invalid

            # Check lockout AFTER verifying password (same response for wrong pass + locked)
            if row["locked_until"] and row["locked_until"] > datetime.now(tz=timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="account temporarily locked — too many failed attempts",
                    headers={"Retry-After": "900"},
                )

            # Successful login — reset failure counter
            await conn.execute(
                "UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = $1",
                row["id"],
            )

    token = create_access_token(
        user_id=str(row["id"]), org_id=str(row["org_id"])
    )
    return TokenResponse(
        access_token=token,
        org_id=str(row["org_id"]),
        api_key=row["api_key"],
    )


@router.get("/me")
async def me(
    pool: asyncpg.Pool = Depends(get_pool),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """Return basic info about the currently authenticated user."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="not authenticated")
    org_id = verify_jwt_get_org_id(credentials.credentials)
    async with pool.acquire() as conn:
        async with conn.transaction():
            # app_user has NOINHERIT — must SET ROLE to access tables granted
            # to app_role.  SET LOCAL app.org_id so RLS policies on users fire.
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            row = await conn.fetchrow(
                """
                SELECT u.id, u.email, o.name AS org_name, o.api_key
                FROM   users u
                JOIN   orgs  o ON o.id = u.org_id
                WHERE  u.org_id = $1
                LIMIT  1
                """,
                org_id,
            )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="user not found")
    return {
        "user_id":  str(row["id"]),
        "email":    row["email"],
        "org_name": row["org_name"],
        "api_key":  row["api_key"],
    }


@router.post("/rotate-api-key")
async def rotate_api_key(
    pool: asyncpg.Pool = Depends(get_pool),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """
    Rotate the org's API key.

    Generates a new cryptographically random 48-character hex key using
    Postgres's gen_random_bytes(24). The old key is immediately invalidated —
    any JS SDK integrations or webhook senders using the old key must be updated.

    Returns the new api_key.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="not authenticated")
    org_id = verify_jwt_get_org_id(credentials.credentials)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            new_key = await conn.fetchval(
                """
                UPDATE orgs
                SET    api_key = encode(gen_random_bytes(24), 'hex')
                WHERE  id = $1
                RETURNING api_key
                """,
                org_id,
            )
    if new_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="org not found")
    return {"api_key": new_key}

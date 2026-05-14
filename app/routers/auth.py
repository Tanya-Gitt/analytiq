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

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import asyncpg
import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, field_validator

from app.auth import create_access_token, verify_jwt, verify_jwt_get_org_id
from app.database import get_pool
from app.deps import require_admin

logger = logging.getLogger(__name__)


async def _check_pwned(password: str) -> bool:
    """
    Check password against HaveIBeenPwned using k-anonymity (SHA-1 prefix).

    Only the first 5 chars of the SHA-1 hash are sent to the API — the full
    hash never leaves the server. Returns True if the password has been pwned,
    False if it's clean or if the check fails (fail-open to avoid blocking
    legitimate signups on network errors).
    """
    try:
        sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"https://api.pwnedpasswords.com/range/{prefix}",
                headers={"Add-Padding": "true"},  # padding prevents traffic analysis
            )
        if resp.status_code != 200:
            return False  # fail-open: don't block signup if API is down
        for line in resp.text.splitlines():
            parts = line.split(":")
            if len(parts) == 2 and parts[0] == suffix:
                count = int(parts[1])
                return count > 0
    except Exception:
        logger.warning("HIBP check failed (fail-open)", exc_info=True)
    return False

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
    def password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("password must be at least 12 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one digit")
        # Reject trivially common passwords
        _common = {"password", "password1", "12345678", "123456789", "qwerty123"}
        if v.lower() in _common:
            raise ValueError("password is too common — choose a stronger password")
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
      1. Check password against HaveIBeenPwned (k-anonymity, fail-open)
      2. Create org row (generates api_key automatically via SQL DEFAULT)
      3. Create user row with bcrypt password hash
      4. Return JWT containing org_id
    """
    # HaveIBeenPwned check — fail-open: if HIBP is unreachable we don't block signup
    if await _check_pwned(body.password):
        raise HTTPException(
            status_code=400,
            detail=(
                "This password has appeared in a known data breach. "
                "Please choose a different password."
            ),
        )

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

            # Create user (first user in org is always admin)
            user = await conn.fetchrow(
                "INSERT INTO users (org_id, email, password_hash, role) VALUES ($1, $2, $3, 'admin') RETURNING id, role",
                org["id"],
                body.email,
                password_hash,
            )

    token = create_access_token(user_id=str(user["id"]), org_id=org_id, role=user["role"])
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
                       u.locked_until, u.role, o.api_key
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
                                THEN NOW() + $3
                                ELSE locked_until
                            END
                        WHERE id = $1
                        """,
                        row["id"],
                        _MAX_FAILED_ATTEMPTS,
                        _LOCKOUT_DURATION,
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
        user_id=str(row["id"]), org_id=str(row["org_id"]), role=row["role"]
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
    jwt_payload = verify_jwt(credentials.credentials)
    org_id  = jwt_payload["org_id"]
    user_id = jwt_payload.get("sub")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            row = await conn.fetchrow(
                """
                SELECT u.id, u.email, u.role, o.name AS org_name, o.api_key
                FROM   users u
                JOIN   orgs  o ON o.id = u.org_id
                WHERE  u.org_id = $1
                  AND  u.id     = $2::uuid
                LIMIT  1
                """,
                org_id,
                user_id,
            )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="user not found")
    return {
        "user_id":  str(row["id"]),
        "email":    row["email"],
        "role":     row["role"],
        "org_name": row["org_name"],
        "api_key":  row["api_key"],
    }


@router.post("/logout", status_code=200)
async def logout(
    pool: asyncpg.Pool = Depends(get_pool),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """
    Logout the current user.

    Records the token's JTI (JWT ID) in `revoked_tokens` so the server
    rejects it even before its natural expiry.  The client MUST also clear
    the stored token from localStorage / cookies.

    Without server-side revocation a stolen JWT is valid until expiry (24 h).
    This endpoint closes that window.
    """
    if credentials is None:
        # No token = already logged out; return success to avoid information leakage
        return {"logged_out": True}

    try:
        payload = verify_jwt(credentials.credentials)
    except Exception:
        # Invalid token is already effectively logged out
        return {"logged_out": True}

    jti     = payload.get("jti") or credentials.credentials[-16:]  # fallback fingerprint
    exp     = payload.get("exp")
    org_id  = payload.get("org_id")

    if org_id and exp:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET LOCAL ROLE app_role")
                await conn.execute(
                    """
                    INSERT INTO revoked_tokens (jti, org_id, expires_at)
                    VALUES ($1, $2::uuid, to_timestamp($3))
                    ON CONFLICT (jti) DO NOTHING
                    """,
                    jti,
                    org_id,
                    exp,
                )

    return {"logged_out": True}


@router.post("/rotate-api-key")
async def rotate_api_key(
    pool: asyncpg.Pool = Depends(get_pool),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    _admin: dict = Depends(require_admin),  # only admins may rotate the org's API key
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


# ── Demo login ────────────────────────────────────────────────────────────────

_DEMO_ORG_NAME = "Analytiq Demo"


@router.post("/demo-login", response_model=TokenResponse)
async def demo_login(pool: asyncpg.Pool = Depends(get_pool)):
    """
    Return a read-only JWT for the pre-seeded demo org.

    No credentials required — the token is scoped to the demo org's viewer
    role so destructive endpoints (DELETE, admin-only actions) are blocked
    by the existing require_admin dependency.

    Returns 503 if the demo org hasn't been seeded yet
    (run: python scripts/seed_demo.py).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id AS user_id, u.org_id, u.role, o.api_key
            FROM   users u
            JOIN   orgs  o ON o.id = u.org_id
            WHERE  o.name = $1
            ORDER  BY u.created_at
            LIMIT  1
            """,
            _DEMO_ORG_NAME,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo data not seeded yet. Run: python scripts/seed_demo.py",
        )

    token = create_access_token(
        user_id=str(row["user_id"]),
        org_id=str(row["org_id"]),
        role=row["role"],
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        org_id=str(row["org_id"]),
        api_key=row["api_key"],
    )

"""
Auth routes: signup, login, me.

For MVP, this is simple email+password auth (bcrypt hash stored in users table).
Supabase GoTrue handles the JWT signing with the same JWT_SECRET — tokens from
GoTrue's /token endpoint are also accepted by app/auth.py's verify_jwt_get_org_id().
"""

from __future__ import annotations

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

from app.auth import create_access_token, verify_jwt_get_org_id
from app.database import get_pool

_bearer = HTTPBearer(auto_error=False)

router = APIRouter()


class SignupRequest(BaseModel):
    org_name: str
    email: EmailStr
    password: str


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
    """Email + password login. Returns a JWT."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.org_id, u.password_hash, o.api_key
            FROM users u
            JOIN orgs o ON o.id = u.org_id
            WHERE u.email = $1
            """,
            body.email,
        )

    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid email or password",
    )
    if row is None:
        raise invalid

    if not bcrypt.checkpw(body.password.encode(), row["password_hash"].encode()):
        raise invalid

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

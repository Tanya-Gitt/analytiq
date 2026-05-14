"""
Team management API — invite members, list team, remove members.

POST   /api/team/invite          — send invite email (admin only)
GET    /api/team/members         — list members + pending invites
DELETE /api/team/members/{id}    — remove a member (admin only, cannot remove self)
PATCH  /api/team/members/{id}    — change a member's role (admin only)

Public invite endpoints (no auth):
GET    /api/invite/{token}       — get invite metadata (org name, role)
POST   /api/invite/{token}/accept — create account and join the org
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator

from app.audit_log import log_action
from app.auth import create_access_token
from app.database import get_pool
from app.deps import get_org_db, require_admin
from app.notifications import send_email

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class InviteRequest(BaseModel):
    email: EmailStr
    role:  str = "viewer"

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("admin", "viewer"):
            raise ValueError("role must be 'admin' or 'viewer'")
        return v


class AcceptInviteRequest(BaseModel):
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
        _common = {"password", "password1", "12345678", "123456789", "qwerty123"}
        if v.lower() in _common:
            raise ValueError("password is too common — choose a stronger password")
        return v


class PatchRoleRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("admin", "viewer"):
            raise ValueError("role must be 'admin' or 'viewer'")
        return v


# ── Authenticated endpoints ───────────────────────────────────────────────────

@router.post("/team/invite", status_code=status.HTTP_201_CREATED)
async def invite_member(
    body: InviteRequest,
    current_user: dict = Depends(require_admin),
    db: asyncpg.Connection = Depends(get_org_db),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Create and email a team invite.  Admin only."""
    org_id  = current_user["org_id"]
    user_id = current_user["sub"]

    # Check not already a member
    existing_user = await db.fetchval(
        "SELECT id FROM users WHERE email = $1 AND org_id = $2::uuid",
        body.email, org_id,
    )
    if existing_user:
        raise HTTPException(409, "user is already a member of this org")

    # Upsert invite (resend if pending invite for same email exists)
    row = await db.fetchrow(
        """
        INSERT INTO org_invites (org_id, email, role, invited_by)
        VALUES (current_setting('app.org_id')::uuid, $1, $2, $3::uuid)
        ON CONFLICT (token) DO NOTHING
        RETURNING id, token, email, role, expires_at
        """,
        body.email, body.role, user_id,
    )
    if row is None:
        # Rare token collision — regenerate
        row = await db.fetchrow(
            """
            INSERT INTO org_invites (org_id, email, role, invited_by,
                                     token)
            VALUES (current_setting('app.org_id')::uuid, $1, $2, $3::uuid,
                    encode(gen_random_bytes(16), 'hex'))
            RETURNING id, token, email, role, expires_at
            """,
            body.email, body.role, user_id,
        )

    # Fetch org name for the email
    org_name = await db.fetchval(
        "SELECT name FROM orgs WHERE id = current_setting('app.org_id')::uuid"
    )

    # Fire-and-forget invite email
    invite_url = f"/invite/{row['token']}"
    try:
        await send_email(
            to=[body.email],
            subject=f"You've been invited to join {org_name} on Analytiq",
            body=(
                f"<p>You've been invited to join <strong>{org_name}</strong> "
                f"as a <strong>{body.role}</strong>.</p>"
                f"<p><a href='{invite_url}'>Accept invite</a></p>"
                f"<p><small>Expires {row['expires_at'].strftime('%Y-%m-%d')}.</small></p>"
            ),
            html=True,
        )
    except Exception:
        pass  # Email failure doesn't block the invite being created

    await log_action(db, user_id, "member.invited",
                     resource_type="user", resource_id=str(row["id"]),
                     metadata={"email": body.email, "role": body.role})

    return {
        "id":         str(row["id"]),
        "email":      row["email"],
        "role":       row["role"],
        "expires_at": row["expires_at"].isoformat(),
        "invite_url": invite_url,
    }


@router.get("/team/members")
async def list_members(
    db: asyncpg.Connection = Depends(get_org_db),
):
    """List current members and pending invites for the org."""
    members = await db.fetch(
        """
        SELECT id, email, role, created_at
        FROM   users
        WHERE  org_id = current_setting('app.org_id')::uuid
        ORDER  BY created_at
        """
    )

    invites = await db.fetch(
        """
        SELECT id, email, role, expires_at, created_at
        FROM   org_invites
        WHERE  org_id      = current_setting('app.org_id')::uuid
          AND  accepted_at IS NULL
          AND  expires_at  > NOW()
        ORDER  BY created_at DESC
        """
    )

    return {
        "members": [
            {
                "id":         str(m["id"]),
                "email":      m["email"],
                "role":       m["role"],
                "created_at": m["created_at"].isoformat(),
            }
            for m in members
        ],
        "pending_invites": [
            {
                "id":         str(i["id"]),
                "email":      i["email"],
                "role":       i["role"],
                "expires_at": i["expires_at"].isoformat(),
                "created_at": i["created_at"].isoformat(),
            }
            for i in invites
        ],
    }


@router.delete("/team/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: UUID,
    current_user: dict = Depends(require_admin),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Remove a member from the org. Cannot remove yourself."""
    if str(member_id) == current_user["sub"]:
        raise HTTPException(400, "cannot remove yourself")
    removed = await db.fetchrow(
        "DELETE FROM users WHERE id = $1 RETURNING email", member_id
    )
    if removed is None:
        raise HTTPException(404, "member not found")
    await log_action(db, current_user["sub"], "member.removed",
                     resource_type="user", resource_id=str(member_id),
                     metadata={"email": removed["email"]})


@router.patch("/team/members/{member_id}")
async def update_member_role(
    member_id: UUID,
    body: PatchRoleRequest,
    current_user: dict = Depends(require_admin),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Change a member's role. Cannot change your own role."""
    if str(member_id) == current_user["sub"]:
        raise HTTPException(400, "cannot change your own role")
    row = await db.fetchrow(
        "UPDATE users SET role = $1 WHERE id = $2 RETURNING id, email, role",
        body.role, member_id,
    )
    if row is None:
        raise HTTPException(404, "member not found")
    await log_action(db, current_user["sub"], "member.role_changed",
                     resource_type="user", resource_id=str(member_id),
                     metadata={"email": row["email"], "new_role": body.role})
    return {"id": str(row["id"]), "email": row["email"], "role": row["role"]}


@router.delete("/team/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invite(
    invite_id: UUID,
    current_user: dict = Depends(require_admin),
    db: asyncpg.Connection = Depends(get_org_db),
):
    """Cancel a pending invite."""
    result = await db.execute(
        "DELETE FROM org_invites WHERE id = $1",
        invite_id,
    )
    if result == "DELETE 0":
        raise HTTPException(404, "invite not found")


# ── Public invite endpoints ───────────────────────────────────────────────────

@router.get("/invite/{token}")
async def get_invite(
    token: str,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Return invite metadata for the accept-invite page.
    No auth required — the token is the credential.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            # app.org_id not set → SELECT policy's open branch fires
            row = await conn.fetchrow(
                """
                SELECT i.id, i.email, i.role, i.expires_at, i.accepted_at,
                       o.name AS org_name
                FROM   org_invites i
                JOIN   orgs        o ON o.id = i.org_id
                WHERE  i.token = $1
                """,
                token,
            )

    if row is None:
        raise HTTPException(404, "invite not found")
    if row["accepted_at"] is not None:
        raise HTTPException(410, "invite already accepted")
    if datetime.now(timezone.utc) > row["expires_at"]:
        raise HTTPException(410, "invite has expired")

    return {
        "id":       str(row["id"]),
        "email":    row["email"],
        "role":     row["role"],
        "org_name": row["org_name"],
    }


@router.post("/invite/{token}/accept", status_code=status.HTTP_201_CREATED)
async def accept_invite(
    token: str,
    body: AcceptInviteRequest,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Accept a team invite.  Creates the user account and joins the org.
    Returns a JWT so the user is immediately logged in.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")

            # Step 1: Read invite without FOR UPDATE (open SELECT policy; app.org_id not set yet).
            invite = await conn.fetchrow(
                """
                SELECT id, org_id, email, role, expires_at, accepted_at
                FROM   org_invites
                WHERE  token = $1
                """,
                token,
            )

            if invite is None:
                raise HTTPException(404, "invite not found")
            if invite["accepted_at"] is not None:
                raise HTTPException(410, "invite already accepted")
            if datetime.now(timezone.utc) > invite["expires_at"]:
                raise HTTPException(410, "invite has expired")

            org_id = str(invite["org_id"])

            # Step 2: Set org context — all subsequent writes are now scoped.
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")

            # Step 3: Atomically claim the invite (UPDATE policy now passes with org context).
            #         If accepted_at was just set by a concurrent request, this returns 0 rows.
            claimed = await conn.fetchval(
                """
                UPDATE org_invites
                SET    accepted_at = NOW()
                WHERE  id = $1 AND accepted_at IS NULL
                RETURNING id
                """,
                invite["id"],
            )
            if claimed is None:
                raise HTTPException(410, "invite already accepted")

            # Check email not already taken
            existing = await conn.fetchval(
                "SELECT id FROM users WHERE email = $1", invite["email"]
            )
            if existing:
                raise HTTPException(409, "an account with this email already exists")

            password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
            user = await conn.fetchrow(
                """
                INSERT INTO users (org_id, email, password_hash, role)
                VALUES ($1::uuid, $2, $3, $4)
                RETURNING id, role
                """,
                org_id, invite["email"], password_hash, invite["role"],
            )

    token_jwt = create_access_token(
        user_id=str(user["id"]),
        org_id=org_id,
        role=user["role"],
    )
    return {
        "access_token": token_jwt,
        "token_type":   "bearer",
        "org_id":       org_id,
    }

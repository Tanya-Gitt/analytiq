"""
Audit log helper — call log_action() from any router that handles admin operations.
Uses the existing RLS-scoped DB connection so the entry is automatically associated
with the correct org and rolls back if the parent transaction fails.
"""

from __future__ import annotations

import asyncpg


async def log_action(
    db:            asyncpg.Connection,
    actor_id:      str | None,
    action:        str,
    resource_type: str | None = None,
    resource_id:   str | None = None,
    metadata:      dict | None = None,
) -> None:
    actor_email: str | None = None
    if actor_id:
        actor_email = await db.fetchval(
            "SELECT email FROM users WHERE id = $1::uuid", actor_id
        )
    await db.execute(
        """
        INSERT INTO audit_log (org_id, actor_email, action, resource_type, resource_id, metadata)
        VALUES (current_setting('app.org_id')::uuid, $1, $2, $3, $4, $5)
        """,
        actor_email, action, resource_type, resource_id, metadata or {},
    )

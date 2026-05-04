"""
POST /api/webhook/{connector_id} — Segment B real-time webhook ingest.

This is a PUBLIC endpoint authenticated only by HMAC-SHA256 signature.
External systems POST orders here without a JWT — the signature on the
request body (using the per-connector secret) is the authentication.

Flow:
  1. Fetch connector row by ID (no RLS — connector table queried as superuser).
  2. Verify X-Webhook-Signature header with HMAC-SHA256(secret, body).
  3. Parse body (single dict or list of dicts).
  4. Validate required columns (order_id, order_date, quantity).
  5. Open a transaction with SET LOCAL app.org_id, upsert into orders.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.database import get_pool

router = APIRouter()

# Required columns for orders table (NOT NULL in schema)
_REQUIRED_ORDER_COLUMNS = {"order_id", "order_date", "quantity"}


def _verify_hmac(body_bytes: bytes, secret: str, header_value: str) -> None:
    """
    Verify HMAC-SHA256 signature.
    Uses hmac.compare_digest() — timing-safe, prevents timing attacks.

    Header: X-Webhook-Signature: <hex digest>
    Secret: connector.config["secret"]

    Raises HTTP 401 if signature is invalid or missing.
    """
    if not header_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-Webhook-Signature header",
        )
    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    # CRITICAL: compare_digest, NOT ==
    # Python's == short-circuits and leaks timing information.
    if not hmac.compare_digest(expected, header_value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid signature",
        )


@router.post("/webhook/{connector_id}")
async def webhook_ingest(
    connector_id: UUID,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """
    Accept a webhook POST from an external system.
    Body: single row dict or list of row dicts (orders schema).
    Verified by HMAC-SHA256 on the raw request body.

    NOT JWT-authenticated. The per-connector HMAC secret is the auth mechanism.
    """
    # ── 1. fetch connector via SECURITY DEFINER function ──────────────────
    # get_webhook_connector() runs as the schema owner (SECURITY DEFINER),
    # bypassing RLS intentionally — we need org_id and secret BEFORE we can
    # set app.org_id. Only exposes type='webhook' rows by exact id.
    async with pool.acquire() as lookup_conn:
        connector = await lookup_conn.fetchrow(
            "SELECT org_id, config FROM get_webhook_connector($1)",
            connector_id,
        )
    if connector is None:
        raise HTTPException(status_code=404, detail="connector not found")

    org_id: str = str(connector["org_id"])
    config: dict = connector["config"] or {}

    # ── 2. verify HMAC ─────────────────────────────────────────────────────
    body_bytes = await request.body()
    secret: str = config.get("secret", "")
    header_value: str = request.headers.get("x-webhook-signature", "")
    _verify_hmac(body_bytes, secret, header_value)

    # ── 3. parse body ──────────────────────────────────────────────────────
    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    rows: list[dict[str, Any]] = payload if isinstance(payload, list) else [payload]

    if not rows:
        return {"ok": True, "rows_upserted": 0}

    # ── 4. validate required columns ───────────────────────────────────────
    for row in rows:
        missing = _REQUIRED_ORDER_COLUMNS - set(row.keys())
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"missing required column: {', '.join(sorted(missing))}",
            )

    # ── 5. upsert inside RLS transaction ──────────────────────────────────
    def _parse_date(v: Any) -> date | None:
        if v is None:
            return None  # pragma: no cover — JSON order_date is never null (DB NOT NULL)
        if isinstance(v, date):
            return v  # pragma: no cover — JSON deserialises dates as strings, not date objects
        return date.fromisoformat(str(v))

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_id)}'")

            upserted = 0
            for row in rows:
                await conn.execute(
                    """
                    INSERT INTO orders (
                        org_id, order_id, order_date, customer_id, product_id,
                        product_name, channel, quantity, price_per_unit, cost_per_unit,
                        delivered, delivery_time_minutes, region, promo_used,
                        acquisition_source
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15
                    )
                    ON CONFLICT (org_id, order_id) DO UPDATE SET
                        order_date            = EXCLUDED.order_date,
                        quantity              = EXCLUDED.quantity,
                        price_per_unit        = EXCLUDED.price_per_unit,
                        updated_at            = NOW()
                    """,
                    org_id,
                    row.get("order_id"),
                    _parse_date(row.get("order_date")),
                    row.get("customer_id"),
                    row.get("product_id"),
                    row.get("product_name"),
                    row.get("channel"),
                    row.get("quantity"),
                    row.get("price_per_unit"),
                    row.get("cost_per_unit"),
                    row.get("delivered"),
                    row.get("delivery_time_minutes"),
                    row.get("region"),
                    row.get("promo_used"),
                    row.get("acquisition_source"),
                )
                upserted += 1

    return {"ok": True, "rows_upserted": upserted}

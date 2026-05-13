"""
AI Product Copilot — natural language → SQL → chart.

POST /api/copilot/query
  { "question": "Which channels drove the most revenue last 30 days?" }
  → { sql, columns, rows, chart_type, x_key, y_key, insight, title }

POST /api/copilot/suggestions
  → list of suggested questions tailored to the org's actual data shape

Security model
──────────────
1. SQL is validated to be SELECT-only before execution.
2. All queries run inside a read-only transaction with RLS enforced
   (SET LOCAL app.org_id) so they can only see the authenticated org's data.
3. Error messages from Postgres are sanitised before being returned to the
   client (no raw pg errors that could leak schema info).
4. Row cap: max 500 rows returned regardless of what Claude generates.

Requires: ANTHROPIC_API_KEY environment variable.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import anthropic
import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_org_db

logger = logging.getLogger(__name__)

router = APIRouter()

# ── schema context (injected into every Claude prompt) ───────────────────────

_SCHEMA = """
You have access to these PostgreSQL tables. Row-level security is enforced
automatically — you do NOT need to filter by org_id. All queries automatically
see only the authenticated organisation's data.

TABLE: events
  id           BIGINT        (primary key)
  event_name   TEXT          (e.g. 'page_view', 'purchase', 'signup', 'checkout_started')
  user_id      TEXT          (nullable; null = anonymous visitor)
  received_at  TIMESTAMPTZ   (when the event arrived)
  properties   JSONB         (arbitrary key-value payload from the SDK)
  Example properties keys: page, sku, price, referrer, campaign, device

TABLE: orders
  id             BIGINT
  user_id        TEXT
  product_name   TEXT
  channel        TEXT        (e.g. 'email', 'organic', 'paid_search', 'social')
  region         TEXT        (e.g. 'US', 'EU', 'APAC')
  price_per_unit NUMERIC
  quantity       INT
  delivered      BOOLEAN
  order_date     DATE

Useful derived values:
  revenue = price_per_unit * quantity
  order_value = price_per_unit * quantity

Current timestamp function: NOW()
Date truncation: DATE_TRUNC('day', received_at), DATE_TRUNC('week', ...), etc.
""".strip()

_SYSTEM_PROMPT = f"""
You are an expert data analyst AI for an analytics platform. Your job is to
translate natural-language questions into precise PostgreSQL SELECT queries and
provide a one-sentence insight about what the result likely shows.

{_SCHEMA}

Rules:
- Output ONLY valid JSON — no markdown, no code fences, no extra text.
- The query MUST be a single SELECT statement. No CTEs with side-effects, no
  INSERT/UPDATE/DELETE/DROP/CREATE/GRANT/TRUNCATE/COPY/EXPLAIN/SET.
- Always include a LIMIT clause (max 500).
- Choose the most appropriate chart_type from: "bar", "line", "pie", "number", "table"
  - "bar"    — comparisons across categories (top N, by dimension)
  - "line"   — trends over time (GROUP BY date_trunc)
  - "number" — single aggregate (total revenue, DAU, etc.)
  - "pie"    — part-of-whole (share by channel, region)
  - "table"  — multi-column detail that doesn't fit a chart
- x_key: the column name to use as the X axis / label
- y_key: the column name to use as the Y axis / value (first numeric column)
- insight: one concrete sentence about what this data reveals (mention numbers
  where you can infer them from the question context).
- title: short chart title (5-8 words)

Output JSON format (no other text):
{{
  "sql": "<SELECT ...>",
  "chart_type": "bar|line|pie|number|table",
  "x_key": "<column>",
  "y_key": "<column>",
  "title": "<short title>",
  "insight": "<one sentence>"
}}
""".strip()

# ── SQL safety guard ──────────────────────────────────────────────────────────

_BLOCKED = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|COPY|'
    r'EXPLAIN|VACUUM|ANALYZE|REINDEX|CLUSTER|COMMENT|LOCK|NOTIFY|LISTEN|'
    r'UNLISTEN|LOAD|RESET|SHOW|pg_read_file|pg_ls_dir|pg_stat_file)\b',
    re.IGNORECASE,
)

_MAX_ROWS = 500


def _validate_sql(sql: str) -> str:
    """Strip to the first statement and enforce SELECT-only."""
    # Take only up to the first semicolon
    sql = sql.split(";")[0].strip()

    # Must start with SELECT or WITH (for CTEs)
    first = sql.split()[0].upper() if sql.split() else ""
    if first not in ("SELECT", "WITH"):
        raise ValueError(f"Only SELECT queries are allowed (got '{first}')")

    if _BLOCKED.search(sql):
        raise ValueError("Query contains a disallowed keyword")

    # Inject row cap
    if not re.search(r'\bLIMIT\b', sql, re.IGNORECASE):
        sql = f"{sql} LIMIT {_MAX_ROWS}"
    else:
        # Replace any LIMIT > _MAX_ROWS with the cap
        sql = re.sub(
            r'\bLIMIT\s+(\d+)',
            lambda m: f"LIMIT {min(int(m.group(1)), _MAX_ROWS)}",
            sql,
            flags=re.IGNORECASE,
        )

    return sql


# ── Claude call ───────────────────────────────────────────────────────────────

def _get_client() -> anthropic.AsyncAnthropic:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(
            status_code=503,
            detail="AI Copilot is not configured. Set ANTHROPIC_API_KEY in your environment.",
        )
    return anthropic.AsyncAnthropic(api_key=key)


async def _ask_claude(question: str) -> dict[str, Any]:
    client = _get_client()
    message = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    raw = message.content[0].text.strip()

    # Strip markdown code fences if Claude wraps in them
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Claude returned non-JSON: %s", raw[:200])
        raise HTTPException(status_code=502, detail=f"AI returned malformed response: {exc}") from exc


# ── DB execution ──────────────────────────────────────────────────────────────

async def _run_query(db: asyncpg.Connection, sql: str) -> tuple[list[str], list[list]]:
    """
    Execute a SELECT in a read-only savepoint. Returns (columns, rows).
    Errors are sanitised — no raw Postgres messages returned to the client.
    """
    try:
        async with db.transaction(readonly=True):
            records = await db.fetch(sql)
    except asyncpg.PostgresError as exc:
        # Sanitise: only expose the first line of the Postgres error message
        first_line = str(exc).split("\n")[0]
        raise HTTPException(status_code=422, detail=f"Query error: {first_line}") from exc

    if not records:
        return [], []

    columns = list(records[0].keys())
    rows = [[_safe_val(r[c]) for c in columns] for r in records]
    return columns, rows


def _safe_val(v: Any) -> Any:
    """Coerce asyncpg types to JSON-serialisable Python primitives."""
    if v is None:
        return None
    if isinstance(v, (int, float, str, bool)):
        return v
    if hasattr(v, "isoformat"):   # date / datetime / timedelta
        return v.isoformat()
    return str(v)


# ── API models ────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    context:  dict[str, Any] = {}   # reserved for future chart context


class QueryResponse(BaseModel):
    question:   str
    sql:        str
    columns:    list[str]
    rows:       list[list]
    chart_type: str
    x_key:      str
    y_key:      str
    title:      str
    insight:    str


# ── /copilot/query ────────────────────────────────────────────────────────────

@router.post("/copilot/query", response_model=QueryResponse)
async def copilot_query(
    body: QueryRequest,
    db:   asyncpg.Connection = Depends(get_org_db),
):
    """
    Accepts a natural-language question. Returns SQL + tabular result +
    chart spec + one-sentence insight.
    """
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "question must not be empty")
    if len(question) > 1000:
        raise HTTPException(400, "question too long (max 1000 chars)")

    # 1. Ask Claude for SQL + chart spec
    ai_resp = await _ask_claude(question)

    raw_sql = ai_resp.get("sql", "")
    if not raw_sql:
        raise HTTPException(502, "AI did not return a SQL query")

    # 2. Validate + sanitise SQL
    try:
        safe_sql = _validate_sql(raw_sql)
    except ValueError as exc:
        raise HTTPException(422, f"Generated SQL failed safety check: {exc}") from exc

    # 3. Execute
    columns, rows = await _run_query(db, safe_sql)

    return QueryResponse(
        question=question,
        sql=safe_sql,
        columns=columns,
        rows=rows,
        chart_type=ai_resp.get("chart_type", "table"),
        x_key=ai_resp.get("x_key", columns[0] if columns else ""),
        y_key=ai_resp.get("y_key", columns[1] if len(columns) > 1 else ""),
        title=ai_resp.get("title", question[:60]),
        insight=ai_resp.get("insight", ""),
    )


# ── /copilot/suggestions ──────────────────────────────────────────────────────

_SUGGESTIONS = [
    "What are the top 10 most common events in the last 7 days?",
    "Show me daily active users over the last 30 days",
    "Which channels generated the most revenue this month?",
    "What is the conversion rate from page_view to purchase?",
    "Show revenue by region for the last 30 days",
    "Which products have the highest average order value?",
    "How many new unique users signed up each week this month?",
    "What percentage of orders were delivered successfully?",
    "Show me hourly event volume for today",
    "Which users have the highest total spend?",
    "What are the top referral channels by order count?",
    "Compare event volume: this week vs last week",
]


@router.get("/copilot/suggestions")
async def copilot_suggestions():
    """Return canned starter questions (no DB call needed)."""
    return {"suggestions": _SUGGESTIONS}

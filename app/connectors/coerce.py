"""
Pandas-free CSV row type coercion for Segment B connectors.

Uses only stdlib: csv, datetime, decimal.

coerce_row(row, column_map) → dict of Python-typed values ready for asyncpg INSERT.

Column type targets (PostgreSQL):
  order_id              → str          (TEXT)
  order_date            → datetime.date (DATE)
  customer_id           → str | None   (TEXT, nullable)
  product_id            → str | None
  product_name          → str | None
  channel               → str | None
  quantity              → int          (INT NOT NULL)
  price_per_unit        → Decimal|None (NUMERIC)
  cost_per_unit         → Decimal|None
  delivered             → bool | None  (BOOLEAN)
  delivery_time_minutes → int | None   (INT)
  region                → str | None
  promo_used            → bool | None
  acquisition_source    → str | None
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# ── Type coercion helpers ─────────────────────────────────────────────────────

def _to_str(val: str) -> str | None:
    """Strip whitespace; return None for empty strings."""
    v = val.strip()
    return v if v else None


def _to_date(val: str) -> date | None:
    """
    Parse a date string. Tries ISO 8601 (YYYY-MM-DD) first, then common formats.
    Returns None for empty/null-like strings.
    """
    v = val.strip()
    if not v or v.lower() in ("", "null", "none", "n/a", "na"):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {val!r}")


def _to_int(val: str) -> int | None:
    v = val.strip()
    if not v or v.lower() in ("null", "none", "n/a", "na"):
        return None
    try:
        return int(float(v))   # handles "1.0" → 1
    except (ValueError, TypeError):
        raise ValueError(f"Cannot parse integer: {val!r}")


def _to_decimal(val: str) -> Decimal | None:
    v = val.strip().replace(",", "")   # strip thousands separators
    if not v or v.lower() in ("null", "none", "n/a", "na"):
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        raise ValueError(f"Cannot parse numeric: {val!r}")


def _to_bool(val: str) -> bool | None:
    v = val.strip().lower()
    if not v or v in ("null", "none", "n/a", "na"):
        return None
    if v in ("true", "yes", "1", "y", "t"):
        return True
    if v in ("false", "no", "0", "n", "f"):
        return False
    raise ValueError(f"Cannot parse boolean: {val!r}")


# Maps orders column name → coercion function
_COLUMN_COERCERS: dict[str, Any] = {
    "order_id":              _to_str,
    "order_date":            _to_date,
    "customer_id":           _to_str,
    "product_id":            _to_str,
    "product_name":          _to_str,
    "channel":               _to_str,
    "quantity":              _to_int,
    "price_per_unit":        _to_decimal,
    "cost_per_unit":         _to_decimal,
    "delivered":             _to_bool,
    "delivery_time_minutes": _to_int,
    "region":                _to_str,
    "promo_used":            _to_bool,
    "acquisition_source":    _to_str,
}


# ── Public API ────────────────────────────────────────────────────────────────

def coerce_row(raw_row: dict[str, str], column_map: dict[str, str]) -> dict[str, Any]:
    """
    Apply column_map to a raw CSV row dict and coerce values to Python types.

    Args:
        raw_row:    Dict of {csv_header: raw_string_value} from csv.DictReader.
        column_map: Dict of {csv_header: orders_column_name} from connector config.

    Returns:
        Dict of {orders_column_name: typed_python_value}.

    Raises:
        ValueError: if a required column value fails type coercion.
        KeyError:   if a csv_header in column_map is absent from raw_row.
    """
    result: dict[str, Any] = {}
    for csv_header, db_column in column_map.items():
        raw_val = raw_row.get(csv_header, "")
        coercer = _COLUMN_COERCERS.get(db_column, _to_str)
        try:
            result[db_column] = coercer(raw_val)
        except ValueError as e:
            raise ValueError(f"Column {db_column!r} (from CSV header {csv_header!r}): {e}") from e
    return result


def parse_csv_rows(
    csv_bytes: bytes,
    column_map: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Parse a CSV byte string into a list of coerced row dicts.

    Skips rows where all mapped values are empty (blank lines).
    Raises ValueError on the first row that fails coercion (includes row number).
    """
    text = csv_bytes.decode("utf-8-sig")  # strip BOM if present (Excel exports)
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []

    for i, raw_row in enumerate(reader, start=2):  # row 1 = header
        try:
            coerced = coerce_row(raw_row, column_map)
        except (ValueError, KeyError) as e:
            raise ValueError(f"Row {i}: {e}") from e

        # Skip entirely-empty rows
        if all(v is None for v in coerced.values()):
            continue

        rows.append(coerced)

    return rows

"""
Tests for app/connectors/coerce.py — type coercion helpers and public API.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.connectors.coerce import coerce_row, parse_csv_rows

# ── coerce_row ─────────────────────────────────────────────────────────────────

class TestCoerceRow:
    def _map(self, **kwargs):
        """Build a column_map where csv_header == db_column for simplicity."""
        return {k: k for k in kwargs}

    def test_str_stripped(self):
        result = coerce_row({"order_id": "  ORD-1  "}, {"order_id": "order_id"})
        assert result["order_id"] == "ORD-1"

    def test_str_empty_returns_none(self):
        result = coerce_row({"customer_id": "   "}, {"customer_id": "customer_id"})
        assert result["customer_id"] is None

    # date parsing
    def test_date_iso(self):
        result = coerce_row({"order_date": "2024-03-15"}, {"order_date": "order_date"})
        assert result["order_date"] == date(2024, 3, 15)

    def test_date_us_format(self):
        result = coerce_row({"order_date": "03/15/2024"}, {"order_date": "order_date"})
        assert result["order_date"] == date(2024, 3, 15)

    def test_date_dmy_slash(self):
        result = coerce_row({"order_date": "15/03/2024"}, {"order_date": "order_date"})
        assert result["order_date"] == date(2024, 3, 15)

    def test_date_null_string_returns_none(self):
        for null_val in ("null", "NULL", "none", "None", "n/a", "N/A", "na", ""):
            result = coerce_row({"order_date": null_val}, {"order_date": "order_date"})
            assert result["order_date"] is None, f"Expected None for {null_val!r}"

    def test_date_invalid_raises(self):
        with pytest.raises(ValueError, match="order_date"):
            coerce_row({"order_date": "not-a-date"}, {"order_date": "order_date"})

    # int parsing
    def test_int_plain(self):
        result = coerce_row({"quantity": "42"}, {"quantity": "quantity"})
        assert result["quantity"] == 42

    def test_int_float_string(self):
        result = coerce_row({"quantity": "3.0"}, {"quantity": "quantity"})
        assert result["quantity"] == 3

    def test_int_null_returns_none(self):
        result = coerce_row({"delivery_time_minutes": "null"}, {"delivery_time_minutes": "delivery_time_minutes"})
        assert result["delivery_time_minutes"] is None

    def test_int_invalid_raises(self):
        with pytest.raises(ValueError, match="quantity"):
            coerce_row({"quantity": "not_an_int"}, {"quantity": "quantity"})

    # decimal parsing
    def test_decimal_plain(self):
        result = coerce_row({"price_per_unit": "19.99"}, {"price_per_unit": "price_per_unit"})
        assert result["price_per_unit"] == Decimal("19.99")

    def test_decimal_thousands_separator(self):
        result = coerce_row({"price_per_unit": "1,299.99"}, {"price_per_unit": "price_per_unit"})
        assert result["price_per_unit"] == Decimal("1299.99")

    def test_decimal_null_returns_none(self):
        result = coerce_row({"cost_per_unit": ""}, {"cost_per_unit": "cost_per_unit"})
        assert result["cost_per_unit"] is None

    def test_decimal_invalid_raises(self):
        with pytest.raises(ValueError, match="price_per_unit"):
            coerce_row({"price_per_unit": "$19.99"}, {"price_per_unit": "price_per_unit"})

    # bool parsing
    @pytest.mark.parametrize("val,expected", [
        ("true", True), ("True", True), ("TRUE", True),
        ("yes", True), ("1", True), ("y", True), ("t", True),
        ("false", False), ("False", False), ("FALSE", False),
        ("no", False), ("0", False), ("n", False), ("f", False),
    ])
    def test_bool_truthy_falsy(self, val, expected):
        result = coerce_row({"delivered": val}, {"delivered": "delivered"})
        assert result["delivered"] is expected

    def test_bool_null_returns_none(self):
        result = coerce_row({"promo_used": "n/a"}, {"promo_used": "promo_used"})
        assert result["promo_used"] is None

    def test_bool_invalid_raises(self):
        with pytest.raises(ValueError, match="delivered"):
            coerce_row({"delivered": "maybe"}, {"delivered": "delivered"})

    # unknown db column defaults to _to_str
    def test_unknown_column_defaults_to_str(self):
        result = coerce_row({"weird_col": "  hello  "}, {"weird_col": "weird_col"})
        assert result["weird_col"] == "hello"

    # column_map remapping
    def test_column_map_renames(self):
        raw_row = {"Date": "2024-01-01", "Units": "5", "SKU": "ABC"}
        column_map = {"Date": "order_date", "Units": "quantity", "SKU": "product_id"}
        result = coerce_row(raw_row, column_map)
        assert result["order_date"] == date(2024, 1, 1)
        assert result["quantity"] == 5
        assert result["product_id"] == "ABC"

    def test_missing_csv_header_treated_as_empty(self):
        # raw_row.get(csv_header, "") returns "" for absent keys
        result = coerce_row({}, {"some_col": "customer_id"})
        assert result["customer_id"] is None

    def test_error_message_includes_column_name(self):
        with pytest.raises(ValueError) as exc_info:
            coerce_row({"qty": "bad"}, {"qty": "quantity"})
        assert "quantity" in str(exc_info.value)
        assert "qty" in str(exc_info.value)


# ── parse_csv_rows ─────────────────────────────────────────────────────────────

class TestParseCsvRows:
    def _csv(self, *rows: str) -> bytes:
        return "\n".join(rows).encode()

    def test_basic_parse(self):
        csv_bytes = self._csv(
            "Date,Units,Price",
            "2024-01-01,10,9.99",
            "2024-01-02,5,19.99",
        )
        column_map = {"Date": "order_date", "Units": "quantity", "Price": "price_per_unit"}
        rows = parse_csv_rows(csv_bytes, column_map)
        assert len(rows) == 2
        assert rows[0]["order_date"] == date(2024, 1, 1)
        assert rows[0]["quantity"] == 10
        assert rows[1]["price_per_unit"] == Decimal("19.99")

    def test_skips_all_null_rows(self):
        csv_bytes = self._csv(
            "order_id,quantity",
            "ORD-1,5",
            ",",          # all-null row — should be skipped
            "ORD-2,3",
        )
        column_map = {"order_id": "order_id", "quantity": "quantity"}
        rows = parse_csv_rows(csv_bytes, column_map)
        assert len(rows) == 2

    def test_bom_stripped(self):
        """Excel CSV exports often have a UTF-8 BOM prefix."""
        csv_bytes = b"\xef\xbb\xbforder_id,quantity\nORD-1,7\n"
        rows = parse_csv_rows(csv_bytes, {"order_id": "order_id", "quantity": "quantity"})
        assert len(rows) == 1
        assert rows[0]["order_id"] == "ORD-1"

    def test_error_includes_row_number(self):
        csv_bytes = self._csv(
            "order_id,quantity",
            "ORD-1,5",
            "ORD-2,bad_int",   # row 3 (1=header, 2=first data, 3=second data)
        )
        column_map = {"order_id": "order_id", "quantity": "quantity"}
        with pytest.raises(ValueError, match=r"Row 3"):
            parse_csv_rows(csv_bytes, column_map)

    def test_empty_csv_returns_empty_list(self):
        csv_bytes = b"order_id,quantity\n"
        rows = parse_csv_rows(csv_bytes, {"order_id": "order_id", "quantity": "quantity"})
        assert rows == []

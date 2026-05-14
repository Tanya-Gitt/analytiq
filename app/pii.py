"""
PII Detection + Auto-redaction

Scans event properties for PII patterns and replaces sensitive values
with [REDACTED] before events are stored in the database.

Called from ingest.py: redacted_props, fields = detect_and_redact(props)
"""

from __future__ import annotations

import re

# ── Patterns ──────────────────────────────────────────────────────────────────

_EMAIL_RE    = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')
_PHONE_RE    = re.compile(r'\b(\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b')
_SSN_RE      = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
_CC_RE       = re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b')
_IP_RE       = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
_JWT_RE      = re.compile(r'\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]*\b')

_SENSITIVE_FIELD_NAMES = frozenset({
    'email', 'phone', 'mobile', 'ssn', 'social_security', 'credit_card',
    'card_number', 'cvv', 'password', 'passwd', 'secret', 'token',
    'api_key', 'apikey', 'access_token', 'refresh_token', 'private_key',
})

_REDACTED = '[REDACTED]'
_MAX_DEPTH = 3


def _field_is_sensitive(field_name: str) -> bool:
    """True if the field name itself indicates PII."""
    lower = field_name.lower()
    return any(s in lower for s in _SENSITIVE_FIELD_NAMES)


def _value_contains_pii(value: str) -> bool:
    """True if the string value matches any PII pattern."""
    return bool(
        _EMAIL_RE.search(value)
        or _PHONE_RE.search(value)
        or _SSN_RE.search(value)
        or _CC_RE.search(value)
        or _JWT_RE.search(value)
    )


def _redact_dict(props: dict, depth: int = 0) -> tuple[dict, list[str]]:
    """
    Recursively redact PII from a dict.
    Returns (redacted_dict, list_of_redacted_field_paths).
    """
    if depth > _MAX_DEPTH:
        return props, []

    result: dict = {}
    redacted_fields: list[str] = []

    for key, value in props.items():
        if isinstance(value, dict):
            redacted_value, nested_fields = _redact_dict(value, depth + 1)
            result[key] = redacted_value
            redacted_fields.extend(f"{key}.{f}" for f in nested_fields)
        elif isinstance(value, str):
            if _field_is_sensitive(key) or _value_contains_pii(value):
                result[key] = _REDACTED
                redacted_fields.append(key)
            else:
                result[key] = value
        else:
            result[key] = value

    return result, redacted_fields


def detect_and_redact(properties: dict) -> tuple[dict, list[str]]:
    """
    Scan `properties` for PII and replace detected values with [REDACTED].

    Returns:
        (redacted_properties, list_of_field_names_that_were_redacted)

    If no PII is found, returns the original dict unchanged and an empty list.
    """
    if not properties:
        return properties, []
    redacted, fields = _redact_dict(properties)
    return redacted, fields

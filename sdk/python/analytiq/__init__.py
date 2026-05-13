"""
Analytics Platform — Python Server SDK

Supports both sync and async usage. Zero required dependencies beyond
the standard library; uses `urllib.request` for sync calls.
For async, `httpx` is used if installed, otherwise falls back to
`asyncio` + `urllib`.

Usage (sync):
    from analytiq import Analytics
    client = Analytics("YOUR_API_KEY")
    client.track("purchase", user_id="u_123", properties={"sku": "PROD-1", "price": 29.99})
    client.identify("u_123", {"email": "alice@example.com", "plan": "pro"})
    client.page(user_id="u_123", properties={"url": "/checkout"})

Usage (async):
    from analytiq import AsyncAnalytics
    client = AsyncAnalytics("YOUR_API_KEY")
    await client.track("purchase", user_id="u_123", properties={"sku": "PROD-1"})
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

__version__ = "0.1.0"
__all__ = ["Analytics", "AsyncAnalytics", "AnalyticsError"]


class AnalyticsError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


# ── Sync client ───────────────────────────────────────────────────────────────

class Analytics:
    """
    Synchronous analytics client. Thread-safe — a single instance can be
    shared across threads (one urllib request per call, no shared state).
    """

    def __init__(
        self,
        api_key: str,
        host: str = "https://your-analytics-host.com",
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._url = f"{host.rstrip('/')}/api/ingest/{api_key}"
        self._timeout = timeout

    # ── public methods ────────────────────────────────────────────────────────

    def track(
        self,
        event: str,
        *,
        user_id: str | None = None,
        anonymous_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Record a named action performed by a user."""
        self._send({
            "type":        "track",
            "event":       event,
            "userId":      user_id,
            "anonymousId": anonymous_id,
            "properties":  properties or {},
        })

    def identify(
        self,
        user_id: str,
        traits: dict[str, Any] | None = None,
    ) -> None:
        """Associate traits (email, plan, etc.) with a user."""
        self._send({
            "type":       "identify",
            "userId":     user_id,
            "properties": traits or {},
        })

    def page(
        self,
        *,
        user_id: str | None = None,
        anonymous_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Record a page view."""
        self._send({
            "type":        "page",
            "userId":      user_id,
            "anonymousId": anonymous_id,
            "properties":  properties or {},
        })

    # ── internals ─────────────────────────────────────────────────────────────

    def _send(self, payload: dict[str, Any]) -> None:
        body = json.dumps({k: v for k, v in payload.items() if v is not None}).encode()
        req = urllib.request.Request(
            self._url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout):
                pass
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            try:
                detail = json.loads(raw).get("detail", raw)
            except Exception:
                detail = raw
            raise AnalyticsError(exc.code, detail) from exc


# ── Async client ──────────────────────────────────────────────────────────────

class AsyncAnalytics:
    """
    Async analytics client for use with asyncio / FastAPI / Django async views.
    Uses httpx if available, otherwise falls back to asyncio + urllib (blocking
    call wrapped in run_in_executor so the event loop is not blocked).
    """

    def __init__(
        self,
        api_key: str,
        host: str = "https://your-analytics-host.com",
        timeout: float = 10.0,
    ) -> None:
        self._sync = Analytics(api_key, host=host, timeout=timeout)
        self._httpx_client: Any = None
        self._url = self._sync._url

        try:
            import httpx  # type: ignore[import]
            self._httpx_client = httpx.AsyncClient(timeout=timeout)
        except ImportError:
            pass

    async def track(
        self,
        event: str,
        *,
        user_id: str | None = None,
        anonymous_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        await self._send({
            "type":        "track",
            "event":       event,
            "userId":      user_id,
            "anonymousId": anonymous_id,
            "properties":  properties or {},
        })

    async def identify(
        self,
        user_id: str,
        traits: dict[str, Any] | None = None,
    ) -> None:
        await self._send({
            "type":       "identify",
            "userId":     user_id,
            "properties": traits or {},
        })

    async def page(
        self,
        *,
        user_id: str | None = None,
        anonymous_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        await self._send({
            "type":        "page",
            "userId":      user_id,
            "anonymousId": anonymous_id,
            "properties":  properties or {},
        })

    async def aclose(self) -> None:
        if self._httpx_client is not None:
            await self._httpx_client.aclose()

    async def __aenter__(self) -> "AsyncAnalytics":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def _send(self, payload: dict[str, Any]) -> None:
        clean = {k: v for k, v in payload.items() if v is not None}
        if self._httpx_client is not None:
            import httpx  # type: ignore[import]
            try:
                resp = await self._httpx_client.post(self._url, json=clean)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                try:
                    detail = exc.response.json().get("detail", str(exc))
                except Exception:
                    detail = str(exc)
                raise AnalyticsError(exc.response.status_code, detail) from exc
        else:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync._send, payload)

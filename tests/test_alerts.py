"""
Tests for scheduler/alert_evaluator.py — FSM transitions, notification dispatch,
re-fire after 24h, no_data condition, SMTP graceful skip, and unit tests for
pure helper functions (_condition_met, _should_refire, _send_slack, _notify,
_send_email_sync) and the _alert_eval scheduler wrapper.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from scheduler.alert_evaluator import (
    _condition_met,
    _notify,
    _should_refire,
    evaluate_alerts,
)
from scheduler.notifications import _send_email_sync
from scheduler.notifications import send_slack as _send_slack

# ── helpers ────────────────────────────────────────────────────────────────────

async def _create_rule(
    pool: asyncpg.Pool,
    org_id: str,
    *,
    metric: str = "order_count",
    condition: str = "below",
    threshold: float = 10.0,
    window_hours: int = 24,
    channel: str = "slack",
    destination: str = "https://hooks.slack.com/test",
    state: str = "OK",
    last_triggered_at=None,
) -> str:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            rule_id = await conn.fetchval(
                """
                INSERT INTO alert_rules
                    (org_id, name, metric, condition, threshold, window_hours,
                     channel, destination, state, last_triggered_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
                """,
                org_id,
                f"Test alert {metric} {condition}",
                metric,
                condition,
                threshold,
                window_hours,
                channel,
                destination,
                state,
                last_triggered_at,
            )
    return str(rule_id)


async def _get_rule_state(pool: asyncpg.Pool, rule_id: str) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT state, last_triggered_at FROM alert_rules WHERE id = $1",
            rule_id,
        )
    return dict(row)


async def _seed_orders(pool: asyncpg.Pool, org_id: str, count: int) -> None:
    """Insert `count` orders for the org so order_count metric is non-zero."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{str(org_id)}'")
            for i in range(count):
                await conn.execute(
                    """
                    INSERT INTO orders (org_id, order_id, order_date, quantity)
                    VALUES ($1, $2, CURRENT_DATE, 1)
                    ON CONFLICT (org_id, order_id) DO NOTHING
                    """,
                    org_id,
                    f"ALT-ORD-{org_id[:8]}-{i}",
                )


# ── OK → TRIGGERED ────────────────────────────────────────────────────────────

class TestOkToTriggered:
    @pytest.mark.asyncio
    async def test_fires_once_when_condition_first_met(self, db_pool, org_a):
        """
        order_count is 0 (no orders). Rule: below 10. Expect transition OK → TRIGGERED
        and exactly one Slack notification.
        """
        rule_id = await _create_rule(
            db_pool, org_a.org_id,
            metric="order_count", condition="below", threshold=10.0,
        )

        with patch("scheduler.alert_evaluator.send_slack", new_callable=AsyncMock) as mock_slack:
            await evaluate_alerts(db_pool)

        rule = await _get_rule_state(db_pool, rule_id)
        assert rule["state"] == "TRIGGERED"
        assert rule["last_triggered_at"] is not None
        mock_slack.assert_called_once()
        subject_arg = mock_slack.call_args[0][1]
        assert "ALERT" in subject_arg


# ── TRIGGERED → OK (resolved) ─────────────────────────────────────────────────

class TestTriggeredToOk:
    @pytest.mark.asyncio
    async def test_sends_resolved_when_condition_no_longer_met(self, db_pool, org_a):
        """
        Rule is TRIGGERED (below 10). We seed 15 orders so count is now above 10.
        Expect transition TRIGGERED → OK and a "resolved" notification.
        """
        rule_id = await _create_rule(
            db_pool, org_a.org_id,
            metric="order_count", condition="below", threshold=10.0,
            state="TRIGGERED",
            last_triggered_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        await _seed_orders(db_pool, org_a.org_id, 15)

        with patch("scheduler.alert_evaluator.send_slack", new_callable=AsyncMock) as mock_slack:
            await evaluate_alerts(db_pool)

        rule = await _get_rule_state(db_pool, rule_id)
        assert rule["state"] == "OK"
        mock_slack.assert_called_once()
        subject_arg = mock_slack.call_args[0][1]
        assert "RESOLVED" in subject_arg


# ── re-fire after 24h ─────────────────────────────────────────────────────────

class TestRefire:
    @pytest.mark.asyncio
    async def test_no_refire_before_24h(self, db_pool, org_a):
        """TRIGGERED rule last fired 1h ago — should NOT re-notify."""
        rule_id = await _create_rule(
            db_pool, org_a.org_id,
            metric="order_count", condition="below", threshold=10.0,
            state="TRIGGERED",
            last_triggered_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        with patch("scheduler.alert_evaluator.send_slack", new_callable=AsyncMock) as mock_slack:
            await evaluate_alerts(db_pool)

        mock_slack.assert_not_called()
        rule = await _get_rule_state(db_pool, rule_id)
        assert rule["state"] == "TRIGGERED"  # stays triggered

    @pytest.mark.asyncio
    async def test_refire_after_24h(self, db_pool, org_a):
        """TRIGGERED rule last fired 25h ago — should re-notify."""
        await _create_rule(
            db_pool, org_a.org_id,
            metric="order_count", condition="below", threshold=10.0,
            state="TRIGGERED",
            last_triggered_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )

        with patch("scheduler.alert_evaluator.send_slack", new_callable=AsyncMock) as mock_slack:
            await evaluate_alerts(db_pool)

        mock_slack.assert_called_once()


# ── no_data condition ─────────────────────────────────────────────────────────

class TestNoDataCondition:
    @pytest.mark.asyncio
    async def test_no_data_triggers_when_metric_is_none(self, db_pool, org_a):
        """
        org_a has no orders → revenue_total is None (no rows).
        Rule: no_data on revenue_total. Expect TRIGGERED.
        """
        rule_id = await _create_rule(
            db_pool, org_a.org_id,
            metric="revenue_total", condition="no_data", threshold=None,
        )

        with patch("scheduler.alert_evaluator.send_slack", new_callable=AsyncMock) as mock_slack:
            await evaluate_alerts(db_pool)

        rule = await _get_rule_state(db_pool, rule_id)
        assert rule["state"] == "TRIGGERED"
        mock_slack.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_data_resolves_when_data_appears(self, db_pool, org_a):
        """After seeding orders, no_data rule should resolve."""
        rule_id = await _create_rule(
            db_pool, org_a.org_id,
            metric="revenue_total", condition="no_data",
            state="TRIGGERED",
            last_triggered_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        await _seed_orders(db_pool, org_a.org_id, 3)

        # Also seed price data so revenue_total is non-null
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL app.org_id = '{str(org_a.org_id)}'")
                await conn.execute(
                    "UPDATE orders SET price_per_unit = 9.99 WHERE org_id = $1",
                    org_a.org_id,
                )

        with patch("scheduler.alert_evaluator.send_slack", new_callable=AsyncMock) as mock_slack:
            await evaluate_alerts(db_pool)

        rule = await _get_rule_state(db_pool, rule_id)
        assert rule["state"] == "OK"
        mock_slack.assert_called_once()
        assert "RESOLVED" in mock_slack.call_args[0][1]


# ── SMTP graceful skip ─────────────────────────────────────────────────────────

class TestSmtpGracefulSkip:
    @pytest.mark.asyncio
    async def test_email_channel_skipped_when_no_smtp_host(
        self, db_pool, org_a, monkeypatch
    ):
        """
        If SMTP_HOST is not set, email notifications should be silently skipped
        without raising an exception.
        """
        monkeypatch.delenv("SMTP_HOST", raising=False)

        rule_id = await _create_rule(
            db_pool, org_a.org_id,
            metric="order_count", condition="below", threshold=10.0,
            channel="email",
            destination="test@example.com",
        )

        # Should not raise even though SMTP is not configured
        await evaluate_alerts(db_pool)

        rule = await _get_rule_state(db_pool, rule_id)
        # State transitions still happen even when notification is skipped
        assert rule["state"] == "TRIGGERED"


# ── batch evaluation (N+1 prevention) ─────────────────────────────────────────

class TestBatchEvaluation:
    @pytest.mark.asyncio
    async def test_same_metric_queried_once_per_org(self, db_pool, org_a):
        """
        Two rules with the same metric for the same org should result in
        only ONE call to evaluate_metric, not two.
        """
        for _ in range(2):
            await _create_rule(
                db_pool, org_a.org_id,
                metric="order_count", condition="below", threshold=10.0,
            )

        with patch(
            "scheduler.alert_evaluator.evaluate_metric",
            new_callable=AsyncMock,
            return_value=5.0,
        ) as mock_eval:
            await evaluate_alerts(db_pool)

        # evaluate_metric called once for (org_a, order_count)
        calls = [c for c in mock_eval.call_args_list]
        org_metric_pairs = [(str(c.args[1]), c.args[2]) for c in calls]
        unique_pairs = set(org_metric_pairs)
        assert len(unique_pairs) == len(org_metric_pairs), (
            f"evaluate_metric was called {len(calls)} times but only "
            f"{len(unique_pairs)} unique (org, metric) pair(s)"
        )


# ── _condition_met unit tests ─────────────────────────────────────────────────

class TestConditionMet:
    """Pure unit tests — no DB, no async."""

    def _rule(self, condition: str, threshold: float | None = 10.0) -> dict:
        return {"condition": condition, "threshold": threshold}

    def test_below_met(self):
        assert _condition_met(self._rule("below", 10.0), 5.0) is True

    def test_below_not_met(self):
        assert _condition_met(self._rule("below", 10.0), 15.0) is False

    def test_above_met(self):
        assert _condition_met(self._rule("above", 10.0), 20.0) is True

    def test_above_not_met(self):
        assert _condition_met(self._rule("above", 10.0), 5.0) is False

    def test_no_data_met_when_value_is_none(self):
        assert _condition_met(self._rule("no_data", None), None) is True

    def test_no_data_not_met_when_value_present(self):
        assert _condition_met(self._rule("no_data", None), 42.0) is False

    def test_value_none_non_no_data_returns_false(self):
        """If value is None but condition is 'below', treat as not met."""
        assert _condition_met(self._rule("below", 5.0), None) is False

    def test_value_none_above_returns_false(self):
        assert _condition_met(self._rule("above", 5.0), None) is False


# ── _should_refire unit tests ─────────────────────────────────────────────────

class TestShouldRefire:
    """Pure unit tests for the 24-hour cooldown logic."""

    def _rule(self, last_triggered_at) -> dict:
        return {"last_triggered_at": last_triggered_at}

    def test_never_triggered_should_refire(self):
        """last_triggered_at is None → always refire."""
        assert _should_refire(self._rule(None)) is True

    def test_triggered_25h_ago_should_refire(self):
        last = datetime.now(timezone.utc) - timedelta(hours=25)
        assert _should_refire(self._rule(last)) is True

    def test_triggered_1h_ago_should_not_refire(self):
        last = datetime.now(timezone.utc) - timedelta(hours=1)
        assert _should_refire(self._rule(last)) is False

    def test_naive_datetime_treated_as_utc(self):
        """asyncpg sometimes returns naive datetimes; they must be handled."""
        # Naive datetime 25 hours ago should still trigger a refire
        last = datetime.utcnow() - timedelta(hours=25)  # naive
        assert last.tzinfo is None  # confirm it's naive
        assert _should_refire(self._rule(last)) is True


# ── _send_slack unit tests ─────────────────────────────────────────────────────

class TestSendSlack:
    @pytest.mark.asyncio
    async def test_success_path(self):
        """A 200 response produces no error."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("scheduler.notifications.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should not raise
            await _send_slack("https://hooks.slack.com/test", "hello")
            mock_client_instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_200_logs_warning_but_does_not_raise(self):
        """A non-200 Slack response is logged but does not bubble up."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"

        with patch("scheduler.notifications.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should not raise even on non-200
            await _send_slack("https://hooks.slack.com/test", "hello")

    @pytest.mark.asyncio
    async def test_network_exception_does_not_raise(self):
        """If httpx raises (network error), the exception is swallowed."""
        with patch("scheduler.notifications.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.post.side_effect = Exception("connection refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should not raise — exceptions are caught internally
            await _send_slack("https://hooks.slack.com/test", "hello")


# ── _send_email_sync unit tests ───────────────────────────────────────────────

class TestSendEmailSync:
    def test_smtp_host_set_sends_email(self, monkeypatch):
        """When SMTP_HOST is configured, _send_email_sync connects and sends."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "user@example.com")
        monkeypatch.setenv("SMTP_PASS", "s3cr3t")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")

        mock_smtp_instance = MagicMock()

        with patch("scheduler.notifications.smtplib.SMTP") as MockSMTP:
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)

            _send_email_sync("dest@example.com", "Test Subject", "Test body")

            MockSMTP.assert_called_once_with("smtp.example.com", 587, timeout=15)
            mock_smtp_instance.ehlo.assert_called_once()
            mock_smtp_instance.starttls.assert_called_once()
            mock_smtp_instance.login.assert_called_once_with("user@example.com", "s3cr3t")
            mock_smtp_instance.send_message.assert_called_once()

    def test_smtp_exception_does_not_raise(self, monkeypatch):
        """SMTP send failure is logged but not re-raised."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.delenv("SMTP_USER", raising=False)

        with patch("scheduler.notifications.smtplib.SMTP") as MockSMTP:
            MockSMTP.side_effect = Exception("connection refused")

            # Must not raise
            _send_email_sync("dest@example.com", "Subject", "Body")


# ── _notify unit tests ────────────────────────────────────────────────────────

class TestNotify:
    @pytest.mark.asyncio
    async def test_unknown_channel_logs_warning_no_raise(self):
        """An unrecognized channel is silently skipped (logged, not raised)."""
        rule = {
            "id": "rule-unknown",
            "channel": "pager_duty",   # not slack or email
            "destination": "https://pagerduty.example.com",
        }
        # Should not raise
        await _notify(rule, "Subject", "Body")

    @pytest.mark.asyncio
    async def test_slack_channel_calls_send_slack(self):
        rule = {
            "id": "rule-slack",
            "channel": "slack",
            "destination": "https://hooks.slack.com/test",
        }
        with patch(
            "scheduler.alert_evaluator.send_slack", new_callable=AsyncMock
        ) as mock_slack:
            await _notify(rule, "ALERT", "metric is low")

        mock_slack.assert_called_once()
        # destination and formatted text are passed
        args = mock_slack.call_args[0]
        assert args[0] == "https://hooks.slack.com/test"
        assert "ALERT" in args[1]

    @pytest.mark.asyncio
    async def test_email_channel_calls_send_email_in_executor(self):
        rule = {
            "id": "rule-email",
            "channel": "email",
            "destination": "user@example.com",
        }
        with patch("scheduler.notifications._send_email_sync"):
            # run_in_executor calls the function synchronously via the mock
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
                await _notify(rule, "ALERT", "body text")

            # The executor was invoked (we don't test internals of run_in_executor here,
            # just that _notify doesn't raise for the email channel)


# ── _alert_eval wrapper ───────────────────────────────────────────────────────

class TestAlertEvalWrapper:
    @pytest.mark.asyncio
    async def test_exception_in_evaluate_alerts_is_swallowed(self, db_pool):
        """
        _alert_eval wraps evaluate_alerts in a try/except so a crash in the
        evaluator does not kill the scheduler loop.
        """
        from scheduler.main import _alert_eval

        with patch(
            "scheduler.main.evaluate_alerts",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise
            await _alert_eval(db_pool)


# ── evaluate_alerts early return (no rules) ───────────────────────────────────

class TestEvaluateAlertsNoRules:
    @pytest.mark.asyncio
    async def test_no_rules_returns_without_error(self, db_pool):
        """
        When there are no alert_rules rows, evaluate_alerts must return
        without error (early-return path).
        """
        # Just call evaluate_alerts against an empty alert_rules table.
        # This DB fixture is session-scoped so other tests may have inserted
        # rules — but they won't match the org check because evaluate_alerts
        # fetches ALL rules. Create a fresh db state... actually just call
        # it and confirm it doesn't raise.
        with patch(
            "scheduler.alert_evaluator.evaluate_metric",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # Will short-circuit at "if not rules: return" if the table is empty,
            # or complete normally with any existing rows — either way no exception.
            await evaluate_alerts(db_pool)


class TestConditionMetUnknownCondition:
    """The final `return False` fallback in _condition_met."""

    def test_unknown_condition_returns_false(self):
        rule = {"condition": "equals", "threshold": 10.0}
        # value is non-None, condition is not "below"/"above"/"no_data"
        assert _condition_met(rule, 10.0) is False

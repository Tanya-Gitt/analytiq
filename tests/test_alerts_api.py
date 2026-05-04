"""
Tests for the alerts HTTP API:
  GET    /api/alerts        — list rules for authenticated org
  POST   /api/alerts        — create a rule
  DELETE /api/alerts/{id}   — delete a rule

Coverage:
  - Create a rule, list it, delete it (happy path)
  - Validation: unknown metric, invalid condition, missing threshold
  - Unauthenticated requests are rejected
  - Cross-org isolation: org B cannot see or delete org A's rules
  - no_data condition does not require threshold
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import OrgFixture

# ── helpers ───────────────────────────────────────────────────────────────────

_VALID_RULE = {
    "name": "Low revenue alert",
    "metric": "revenue_total",
    "condition": "below",
    "threshold": 100.0,
    "window_hours": 24,
    "channel": "slack",
    "destination": "https://hooks.slack.com/services/test",
}


class TestCreateAlertRule:
    @pytest.mark.asyncio
    async def test_create_returns_201_with_id(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        resp = await client.post(
            "/api/alerts",
            json=_VALID_RULE,
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["metric"] == "revenue_total"
        assert data["condition"] == "below"
        assert data["threshold"] == 100.0
        assert data["state"] == "OK"

    @pytest.mark.asyncio
    async def test_no_data_condition_no_threshold_required(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        """no_data rules do not require a numeric threshold."""
        resp = await client.post(
            "/api/alerts",
            json={
                "name": "No data alert",
                "metric": "event_count",
                "condition": "no_data",
                "window_hours": 12,
                "channel": "email",
                "destination": "ops@example.com",
            },
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["condition"] == "no_data"

    @pytest.mark.asyncio
    async def test_unknown_metric_returns_422(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        resp = await client.post(
            "/api/alerts",
            json={**_VALID_RULE, "metric": "nonexistent_metric"},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_condition_returns_422(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        resp = await client.post(
            "/api/alerts",
            json={**_VALID_RULE, "condition": "equals"},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_above_below_without_threshold_returns_422(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        """'below'/'above' conditions require a threshold value."""
        resp = await client.post(
            "/api/alerts",
            json={**_VALID_RULE, "threshold": None},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_channel_returns_422(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        resp = await client.post(
            "/api/alerts",
            json={**_VALID_RULE, "channel": "sms"},
            headers=org_a.auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/alerts", json=_VALID_RULE)
        assert resp.status_code == 401


class TestListAlertRules:
    @pytest.mark.asyncio
    async def test_empty_list_on_fresh_org(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        resp = await client.get("/api/alerts", headers=org_a.auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_created_rule_appears_in_list(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        await client.post("/api/alerts", json=_VALID_RULE, headers=org_a.auth_headers)

        resp = await client.get("/api/alerts", headers=org_a.auth_headers)
        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) == 1
        assert rules[0]["name"] == "Low revenue alert"

    @pytest.mark.asyncio
    async def test_multiple_rules_listed(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        for i in range(3):
            await client.post(
                "/api/alerts",
                json={**_VALID_RULE, "name": f"Rule {i}"},
                headers=org_a.auth_headers,
            )

        resp = await client.get("/api/alerts", headers=org_a.auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/alerts")
        assert resp.status_code == 401


class TestDeleteAlertRule:
    @pytest.mark.asyncio
    async def test_delete_returns_204(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        create = await client.post(
            "/api/alerts", json=_VALID_RULE, headers=org_a.auth_headers
        )
        rule_id = create.json()["id"]

        resp = await client.delete(
            f"/api/alerts/{rule_id}", headers=org_a.auth_headers
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_deleted_rule_disappears_from_list(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        create = await client.post(
            "/api/alerts", json=_VALID_RULE, headers=org_a.auth_headers
        )
        rule_id = create.json()["id"]

        await client.delete(f"/api/alerts/{rule_id}", headers=org_a.auth_headers)

        rules = (await client.get("/api/alerts", headers=org_a.auth_headers)).json()
        assert all(r["id"] != rule_id for r in rules)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(
        self, client: AsyncClient, org_a: OrgFixture
    ):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.delete(
            f"/api/alerts/{fake_id}", headers=org_a.auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.delete(f"/api/alerts/{fake_id}")
        assert resp.status_code == 401


class TestAlertOrgIsolation:
    @pytest.mark.asyncio
    async def test_org_b_cannot_see_org_a_rules(
        self, client: AsyncClient, org_a: OrgFixture, org_b: OrgFixture
    ):
        """Rules created by org A must not appear in org B's list."""
        await client.post("/api/alerts", json=_VALID_RULE, headers=org_a.auth_headers)

        rules_b = (await client.get("/api/alerts", headers=org_b.auth_headers)).json()
        assert rules_b == []

    @pytest.mark.asyncio
    async def test_org_b_cannot_delete_org_a_rule(
        self, client: AsyncClient, org_a: OrgFixture, org_b: OrgFixture
    ):
        """DELETE by org B on org A's rule_id must return 404 (RLS hides the row)."""
        create = await client.post(
            "/api/alerts", json=_VALID_RULE, headers=org_a.auth_headers
        )
        rule_id = create.json()["id"]

        # Org B tries to delete org A's rule
        resp = await client.delete(
            f"/api/alerts/{rule_id}", headers=org_b.auth_headers
        )
        assert resp.status_code == 404

        # Rule must still exist for org A
        rules_a = (await client.get("/api/alerts", headers=org_a.auth_headers)).json()
        assert any(r["id"] == rule_id for r in rules_a)

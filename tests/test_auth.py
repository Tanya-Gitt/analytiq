"""
Tests for POST /api/auth/signup, POST /api/auth/login, GET /api/auth/me.

Coverage:
  - Happy path: signup creates org+user, returns JWT with correct shape
  - Duplicate email returns 409
  - Login succeeds with correct credentials, fails with wrong password
  - Login fails for unknown email
  - /me requires a valid Bearer token
  - /me returns the correct user/org info
  - JWT from signup can authenticate subsequent requests
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestSignup:
    @pytest.mark.asyncio
    async def test_signup_returns_201_with_token(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/signup",
            json={
                "org_name": "Test Corp",
                "email": "newuser@example.com",
                "password": "s3cr3tpassword",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "org_id" in data
        assert "api_key" in data

    @pytest.mark.asyncio
    async def test_signup_creates_usable_jwt(self, client: AsyncClient):
        """JWT returned from signup must authenticate /api/auth/me."""
        signup = await client.post(
            "/api/auth/signup",
            json={
                "org_name": "JWT Corp",
                "email": "jwtuser@example.com",
                "password": "password123",
            },
        )
        assert signup.status_code == 201
        token = signup.json()["access_token"]

        me = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200

    @pytest.mark.asyncio
    async def test_duplicate_email_returns_409(self, client: AsyncClient):
        """Signing up with an already-registered email must return 409."""
        payload = {
            "org_name": "Dupe Corp",
            "email": "dupe@example.com",
            "password": "password",
        }
        first = await client.post("/api/auth/signup", json=payload)
        assert first.status_code == 201

        second = await client.post("/api/auth/signup", json=payload)
        assert second.status_code == 409
        assert "already registered" in second.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_email_returns_422(self, client: AsyncClient):
        """Pydantic EmailStr validation must reject malformed email addresses."""
        resp = await client.post(
            "/api/auth/signup",
            json={
                "org_name": "Bad Email Corp",
                "email": "not-an-email",
                "password": "password",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_org_name_in_me_response(self, client: AsyncClient):
        """The org_name provided at signup must be returned by /me."""
        signup = await client.post(
            "/api/auth/signup",
            json={
                "org_name": "Acme Inc",
                "email": "acme@example.com",
                "password": "password",
            },
        )
        assert signup.status_code == 201
        token = signup.json()["access_token"]

        me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["org_name"] == "Acme Inc"


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_returns_token(self, client: AsyncClient):
        """Valid credentials must return a JWT."""
        await client.post(
            "/api/auth/signup",
            json={
                "org_name": "Login Corp",
                "email": "loginuser@example.com",
                "password": "correct_password",
            },
        )

        resp = await client.post(
            "/api/auth/login",
            json={"email": "loginuser@example.com", "password": "correct_password"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, client: AsyncClient):
        await client.post(
            "/api/auth/signup",
            json={
                "org_name": "Wrong Pass Corp",
                "email": "wrongpass@example.com",
                "password": "correct",
            },
        )

        resp = await client.post(
            "/api/auth/login",
            json={"email": "wrongpass@example.com", "password": "wrong"},
        )
        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_unknown_email_returns_401(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "anything"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_token_authenticates_me(self, client: AsyncClient):
        """JWT from /login must be accepted by /me."""
        await client.post(
            "/api/auth/signup",
            json={
                "org_name": "Me Corp",
                "email": "meuser@example.com",
                "password": "pass1234",
            },
        )
        login = await client.post(
            "/api/auth/login",
            json={"email": "meuser@example.com", "password": "pass1234"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "meuser@example.com"

    @pytest.mark.asyncio
    async def test_login_and_signup_return_same_org_id(self, client: AsyncClient):
        """The org_id in the signup response must match the one from /login."""
        signup = await client.post(
            "/api/auth/signup",
            json={
                "org_name": "Same Org",
                "email": "sameorg@example.com",
                "password": "pass",
            },
        )
        signup_org_id = signup.json()["org_id"]

        login = await client.post(
            "/api/auth/login",
            json={"email": "sameorg@example.com", "password": "pass"},
        )
        assert login.json()["org_id"] == signup_org_id


class TestMe:
    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_invalid_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer this.is.not.valid"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_returns_correct_fields(self, client: AsyncClient):
        signup = await client.post(
            "/api/auth/signup",
            json={
                "org_name": "Fields Corp",
                "email": "fields@example.com",
                "password": "password",
            },
        )
        token = signup.json()["access_token"]

        me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        data = me.json()
        assert "user_id" in data
        assert "email" in data
        assert "org_name" in data
        assert "api_key" in data
        assert data["email"] == "fields@example.com"

    @pytest.mark.asyncio
    async def test_me_api_key_matches_signup(self, client: AsyncClient):
        """api_key returned by /me must be the same as the one from /signup."""
        signup = await client.post(
            "/api/auth/signup",
            json={
                "org_name": "Key Match Corp",
                "email": "keymatch@example.com",
                "password": "password",
            },
        )
        signup_data = signup.json()
        token = signup_data["access_token"]
        signup_api_key = signup_data["api_key"]

        me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["api_key"] == signup_api_key


# ── JWT edge cases (covers auth.py lines 34, 67, 71-72) ──────────────────────

class TestJwtEdgeCases:
    """
    Tests for the rarely-hit branches in verify_jwt_get_org_id:
      - JWT with no org_id claim → 401
      - JWT with non-UUID org_id → 401
      - _get_secret() with no JWT_SECRET → RuntimeError (unit test only)
    """

    def _make_token(self, payload: dict) -> str:
        import os

        from jose import jwt as jose_jwt
        secret = os.environ.get("JWT_SECRET", "test-secret-key-for-ci")
        return jose_jwt.encode(payload, secret, algorithm="HS256")

    @pytest.mark.asyncio
    async def test_token_without_org_id_returns_401(self, client: AsyncClient):
        """A properly signed JWT that has no org_id claim must return 401."""
        from datetime import datetime, timedelta, timezone
        token = self._make_token({
            "sub": "some-user-id",
            # org_id intentionally omitted
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        })
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_token_with_invalid_uuid_org_id_returns_401(
        self, client: AsyncClient
    ):
        """A JWT with org_id that is not a valid UUID must return 401."""
        from datetime import datetime, timedelta, timezone
        token = self._make_token({
            "sub": "some-user-id",
            "org_id": "not-a-uuid-at-all",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        })
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_get_secret_raises_when_jwt_secret_unset(self, monkeypatch):
        """_get_secret() raises RuntimeError when JWT_SECRET env var is absent."""
        monkeypatch.delenv("JWT_SECRET", raising=False)
        import pytest as _pytest

        from app.auth import _get_secret
        with _pytest.raises(RuntimeError, match="JWT_SECRET"):
            _get_secret()

    @pytest.mark.asyncio
    async def test_me_returns_404_when_user_deleted(
        self, client: AsyncClient, db_pool, org_a
    ):
        """
        A valid JWT for an org whose user row has been deleted must return 404.
        Covers auth.py line 142 — the defensive 'user not found' guard.
        """

        # Craft a JWT for a non-existent org/user (a random UUID that has no rows)
        import uuid
        from datetime import datetime, timedelta, timezone
        fake_org_id = str(uuid.uuid4())
        token = self._make_token({
            "sub": str(uuid.uuid4()),
            "org_id": fake_org_id,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        })
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

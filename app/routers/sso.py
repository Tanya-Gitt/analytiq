"""
SSO / OAuth 2.0 / OIDC authentication.

Supported providers (out-of-the-box, no per-org config required):
  - Google   — OIDC via accounts.google.com discovery
  - GitHub   — OAuth 2.0 (no OIDC; uses /user API for identity)

Per-org OIDC (requires admin to configure client_id / client_secret):
  - Any OIDC-compliant provider: Okta, Azure AD, Keycloak, Auth0, Ping, …
    Identified by ?provider=oidc&org=<org_id>

Flow
────
  1. Frontend hits GET /api/auth/sso/<provider>/start
     → backend stores a random state in oauth_states, redirects browser to IdP
  2. IdP redirects back to GET /api/auth/sso/callback?state=…&code=…
     → backend verifies state, exchanges code for tokens, resolves user
     → if user exists: issue JWT, redirect to /dashboard
     → if user is new: create user row (JIT provisioning), issue JWT

Environment variables (global providers, set in .env):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET
  APP_BASE_URL   — e.g. https://analytics.example.com  (used to build callback URL)
"""

from __future__ import annotations

import ipaddress
import logging
import os
import secrets
import time
import urllib.parse

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.auth import create_access_token, verify_jwt_get_org_id
from app.database import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)

# ── constants ────────────────────────────────────────────────────────────────

_GOOGLE_DISCOVERY = "https://accounts.google.com"
_GITHUB_AUTH_URL  = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL  = "https://api.github.com/user"
_GITHUB_EMAIL_URL = "https://api.github.com/user/emails"

_SCOPES = {
    "google": "openid email profile",
    "github": "read:user user:email",
}


def _app_base() -> str:
    return os.environ.get("APP_BASE_URL", "http://localhost").rstrip("/")


def _callback_url() -> str:
    return f"{_app_base()}/api/auth/sso/callback"


# ── OIDC discovery cache (fetched once per process per provider) ─────────────

_DISCOVERY_CACHE: dict[str, dict] = {}
_JWKS_CACHE: dict[str, dict] = {}
_CACHE_TTL = 3600  # 1 hour
_CACHE_TS: dict[str, float] = {}


def _validate_discovery_url(url: str) -> None:
    """
    Block SSRF attacks via malicious OIDC discovery URLs.

    Rejects:
      - Non-https schemes (http, file, ftp, etc.)
      - Private / link-local / loopback IP ranges (RFC 1918, RFC 3927, ::1 …)
      - Cloud IMDS endpoints (169.254.169.254, fd00:ec2::254)
      - Empty or unparseable URLs
    """
    if not url:
        raise HTTPException(400, "discovery_url must not be empty")
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        raise HTTPException(400, "discovery_url is not a valid URL")

    if parsed.scheme not in ("https",):
        raise HTTPException(400, "discovery_url must use HTTPS")

    hostname = parsed.hostname or ""
    if not hostname:
        raise HTTPException(400, "discovery_url must have a hostname")

    # Reject bare IP addresses that resolve to private ranges
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise HTTPException(400, "discovery_url must not point to a private/internal address")
        # AWS IMDS and GCP metadata endpoints
        if hostname in ("169.254.169.254", "fd00:ec2::254", "metadata.google.internal"):
            raise HTTPException(400, "discovery_url must not point to a cloud metadata endpoint")
    except ValueError:
        # Not an IP address — hostname-based, allow it
        # (Runtime DNS resolution to a private IP is an edge case
        # mitigated by the network layer; no reliable fix without egress filtering)
        pass

    # Block well-known internal hostnames
    blocked_hosts = {
        "localhost", "postgres", "redis", "db", "internal",
        "metadata.google.internal",
    }
    if hostname.lower() in blocked_hosts:
        raise HTTPException(400, "discovery_url must not point to an internal service")


async def _get_discovery(discovery_base: str) -> dict:
    now = time.monotonic()
    if discovery_base in _DISCOVERY_CACHE and (now - _CACHE_TS.get(discovery_base, 0)) < _CACHE_TTL:
        return _DISCOVERY_CACHE[discovery_base]
    url = f"{discovery_base.rstrip('/')}/.well-known/openid-configuration"
    # Validate before making the request (SSRF guard)
    _validate_discovery_url(url)
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
    data = resp.json()
    _DISCOVERY_CACHE[discovery_base] = data
    _CACHE_TS[discovery_base] = now
    return data


async def _get_jwks(jwks_uri: str) -> list[dict]:
    now = time.monotonic()
    if jwks_uri in _JWKS_CACHE and (now - _CACHE_TS.get(jwks_uri, 0)) < _CACHE_TTL:
        return _JWKS_CACHE[jwks_uri]["keys"]
    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_uri, timeout=10)
        resp.raise_for_status()
    data = resp.json()
    _JWKS_CACHE[jwks_uri] = data
    _CACHE_TS[jwks_uri] = now
    return data["keys"]


async def _verify_id_token(id_token: str, discovery_base: str, client_id: str) -> dict:
    """Verify an OIDC id_token using the provider's JWKS. Returns the claims dict."""
    disc = await _get_discovery(discovery_base)
    jwks  = await _get_jwks(disc["jwks_uri"])
    # Build a JWKS dict that python-jose can consume
    jwks_dict = {"keys": jwks}
    try:
        claims = jwt.decode(
            id_token,
            jwks_dict,
            algorithms=["RS256", "ES256", "RS384", "RS512"],
            audience=client_id,
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        logger.warning("id_token verification failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="id_token verification failed")
    return claims


# ── state helpers ─────────────────────────────────────────────────────────────

async def _create_state(
    pool: asyncpg.Pool,
    provider: str,
    org_id: str | None,
    redirect_to: str = "/dashboard",
) -> str:
    state = secrets.token_hex(32)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO oauth_states (state, provider, org_id, redirect_to)
            VALUES ($1, $2, $3::uuid, $4)
            """,
            state,
            provider,
            org_id,
            redirect_to,
        )
    return state


async def _consume_state(pool: asyncpg.Pool, state: str) -> dict:
    """Pop a state row. Raises 400 if missing or expired."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            DELETE FROM oauth_states
            WHERE state = $1 AND expires_at > NOW()
            RETURNING provider, org_id, redirect_to
            """,
            state,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid or expired OAuth state — please try again",
        )
    return dict(row)


# ── provider config helpers ───────────────────────────────────────────────────

def _global_client(provider: str) -> tuple[str, str]:
    """Return (client_id, client_secret) from environment for global providers."""
    key_prefix = provider.upper()
    client_id     = os.environ.get(f"{key_prefix}_CLIENT_ID", "")
    client_secret = os.environ.get(f"{key_prefix}_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider} SSO is not configured on this instance",
        )
    return client_id, client_secret


async def _org_oidc_config(pool: asyncpg.Pool, org_id: str) -> dict:
    """Return per-org OIDC config row. Raises 404 if not configured."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT client_id, client_secret, discovery_url, provider
            FROM   sso_configs
            WHERE  org_id = $1::uuid AND enabled = TRUE
            LIMIT  1
            """,
            org_id,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO not configured for this organisation",
        )
    return dict(row)


# ── user resolution (JIT provisioning) ───────────────────────────────────────

async def _resolve_user(
    pool: asyncpg.Pool,
    *,
    email: str,
    sso_provider: str,
    sso_sub: str,
    display_name: str | None,
    org_id: str | None,
) -> tuple[str, str, str]:
    """
    Find-or-create a user row for an SSO identity.
    Returns (user_id, org_id, role).

    Rules:
      - Match by (sso_provider, sso_sub) first — handles email changes
      - Fall back to email match within org (links existing local account to SSO)
      - If org_id given: user must belong to that org (enforced by org invite flow)
      - If org_id is None: create a new org named after the user's email domain
        (self-service SSO onboarding)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")

            # 1. Look up by SSO sub
            row = await conn.fetchrow(
                """
                SELECT u.id, u.org_id::text, u.role
                FROM   users u
                WHERE  u.sso_provider = $1
                  AND  u.sso_sub      = $2
                """,
                sso_provider,
                sso_sub,
            )
            if row:
                if org_id and str(row["org_id"]) != org_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="this SSO identity belongs to a different organisation",
                    )
                return str(row["id"]), str(row["org_id"]), str(row["role"])

            # 2. Look up by email (link existing account to SSO)
            if org_id:
                row = await conn.fetchrow(
                    "SELECT id, org_id::text, role FROM users WHERE email = $1 AND org_id = $2::uuid",
                    email, org_id,
                )
                if row:
                    await conn.execute(
                        "UPDATE users SET sso_provider = $1, sso_sub = $2 WHERE id = $3",
                        sso_provider, sso_sub, row["id"],
                    )
                    return str(row["id"]), str(row["org_id"]), str(row["role"])

            # 3. JIT provision: create org + user
            if org_id is None:
                # Auto-create org named after email domain
                domain = email.split("@")[-1] if "@" in email else email
                org_row = await conn.fetchrow(
                    "INSERT INTO orgs (name) VALUES ($1) RETURNING id, api_key",
                    domain,
                )
                org_id = str(org_row["id"])

            user_row = await conn.fetchrow(
                """
                INSERT INTO users (org_id, email, password_hash, sso_provider, sso_sub, role)
                VALUES ($1::uuid, $2, NULL, $3, $4, 'admin')
                RETURNING id, role
                """,
                org_id, email, sso_provider, sso_sub,
            )
            return str(user_row["id"]), org_id, str(user_row["role"])


# ── /start endpoints ──────────────────────────────────────────────────────────

@router.get("/sso/google/start")
async def google_start(
    redirect_to: str = Query(default="/dashboard"),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Redirect browser to Google OAuth consent screen."""
    client_id, _ = _global_client("google")
    disc  = await _get_discovery(_GOOGLE_DISCOVERY)
    state = await _create_state(pool, "google", None, redirect_to)

    params = {
        "client_id":     client_id,
        "redirect_uri":  _callback_url(),
        "response_type": "code",
        "scope":         _SCOPES["google"],
        "state":         state,
        "access_type":   "online",
        "prompt":        "select_account",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{disc['authorization_endpoint']}?{qs}", status_code=302)


@router.get("/sso/github/start")
async def github_start(
    redirect_to: str = Query(default="/dashboard"),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Redirect browser to GitHub OAuth consent screen."""
    client_id, _ = _global_client("github")
    state = await _create_state(pool, "github", None, redirect_to)

    params = {
        "client_id":    client_id,
        "redirect_uri": _callback_url(),
        "scope":        _SCOPES["github"],
        "state":        state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{_GITHUB_AUTH_URL}?{qs}", status_code=302)


@router.get("/sso/oidc/start")
async def oidc_start(
    org_id: str = Query(..., description="Organisation UUID"),
    redirect_to: str = Query(default="/dashboard"),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Redirect browser to the per-org OIDC provider (Okta, Azure AD, etc.)."""
    cfg   = await _org_oidc_config(pool, org_id)
    disc  = await _get_discovery(cfg["discovery_url"])
    state = await _create_state(pool, "oidc", org_id, redirect_to)

    params = {
        "client_id":     cfg["client_id"],
        "redirect_uri":  _callback_url(),
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{disc['authorization_endpoint']}?{qs}", status_code=302)


# ── /callback ─────────────────────────────────────────────────────────────────

@router.get("/sso/callback")
async def sso_callback(
    code:  str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    pool:  asyncpg.Pool = Depends(get_pool),
):
    """
    Universal OAuth callback. Handles Google, GitHub, and generic OIDC.
    On success: redirects to the frontend with ?token=<jwt>&org_id=<uuid>
    On failure: redirects to /login?error=<message>
    """
    base = _app_base()

    if error:
        return RedirectResponse(f"{base}/login?error={error}", status_code=302)

    if not code or not state:
        return RedirectResponse(f"{base}/login?error=missing_code", status_code=302)

    try:
        state_row = await _consume_state(pool, state)
    except HTTPException:
        return RedirectResponse(f"{base}/login?error=invalid_state", status_code=302)

    provider    = state_row["provider"]
    org_id      = state_row["org_id"]
    redirect_to = state_row["redirect_to"] or "/dashboard"

    try:
        if provider == "google":
            user_id, resolved_org_id, role = await _handle_google(pool, code, org_id)
        elif provider == "github":
            user_id, resolved_org_id, role = await _handle_github(pool, code, org_id)
        elif provider == "oidc":
            user_id, resolved_org_id, role = await _handle_oidc(pool, code, org_id)
        else:
            return RedirectResponse(f"{base}/login?error=unknown_provider", status_code=302)
    except HTTPException as exc:
        err = str(exc.detail).replace(" ", "_").lower()
        return RedirectResponse(f"{base}/login?error={err}", status_code=302)

    token = create_access_token(user_id=user_id, org_id=resolved_org_id, role=role)

    # Pass the JWT via URL fragment (#) rather than query string (?).
    # Fragments are NOT sent in HTTP Referer headers and do NOT appear in
    # nginx/server access logs, preventing token leakage to third parties
    # or log aggregators.
    # The frontend's /auth/sso-success page reads window.location.hash.
    dest = redirect_to if redirect_to.startswith("/") else "/dashboard"
    encoded_next = urllib.parse.quote(dest, safe="")
    return RedirectResponse(
        f"{base}/auth/sso-success#token={token}&org_id={resolved_org_id}&next={encoded_next}",
        status_code=302,
    )


# ── provider-specific token exchange ─────────────────────────────────────────

async def _handle_google(
    pool: asyncpg.Pool, code: str, org_id: str | None
) -> tuple[str, str, str]:
    client_id, client_secret = _global_client("google")
    disc = await _get_discovery(_GOOGLE_DISCOVERY)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            disc["token_endpoint"],
            data={
                "code":          code,
                "client_id":     client_id,
                "client_secret": client_secret,
                "redirect_uri":  _callback_url(),
                "grant_type":    "authorization_code",
            },
            timeout=15,
        )
        resp.raise_for_status()
    tokens = resp.json()

    claims = await _verify_id_token(tokens["id_token"], _GOOGLE_DISCOVERY, client_id)
    email  = claims.get("email", "")
    sub    = claims["sub"]
    name   = claims.get("name")

    if not claims.get("email_verified", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Google account email is not verified")

    return await _resolve_user(pool, email=email, sso_provider="google",
                               sso_sub=sub, display_name=name, org_id=org_id)


async def _handle_github(
    pool: asyncpg.Pool, code: str, org_id: str | None
) -> tuple[str, str, str]:
    client_id, client_secret = _global_client("github")

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        resp = await client.post(
            _GITHUB_TOKEN_URL,
            data={
                "client_id":     client_id,
                "client_secret": client_secret,
                "code":          code,
                "redirect_uri":  _callback_url(),
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                                detail="GitHub did not return an access token")

        # Fetch user profile
        headers = {"Authorization": f"token {access_token}", "Accept": "application/json"}
        user_resp  = await client.get(_GITHUB_USER_URL, headers=headers, timeout=10)
        user_resp.raise_for_status()
        user_data = user_resp.json()

        # GitHub may not expose email publicly; fetch via /user/emails
        email = user_data.get("email")
        if not email:
            email_resp = await client.get(_GITHUB_EMAIL_URL, headers=headers, timeout=10)
            email_resp.raise_for_status()
            emails = email_resp.json()
            primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
            if primary:
                email = primary["email"]

    if not email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No verified email on this GitHub account — please add one in GitHub settings",
        )

    sub  = str(user_data["id"])
    name = user_data.get("name") or user_data.get("login")
    return await _resolve_user(pool, email=email, sso_provider="github",
                               sso_sub=sub, display_name=name, org_id=org_id)


async def _handle_oidc(
    pool: asyncpg.Pool, code: str, org_id: str
) -> tuple[str, str, str]:
    cfg  = await _org_oidc_config(pool, org_id)
    disc = await _get_discovery(cfg["discovery_url"])

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            disc["token_endpoint"],
            data={
                "code":          code,
                "client_id":     cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "redirect_uri":  _callback_url(),
                "grant_type":    "authorization_code",
            },
            timeout=15,
        )
        resp.raise_for_status()
    tokens = resp.json()

    claims = await _verify_id_token(tokens["id_token"], cfg["discovery_url"], cfg["client_id"])
    email  = claims.get("email", "")
    sub    = claims["sub"]
    name   = claims.get("name")

    return await _resolve_user(pool, email=email, sso_provider="oidc",
                               sso_sub=sub, display_name=name, org_id=org_id)


# ── SSO config management (admin only) ───────────────────────────────────────

class SSOConfigRequest(BaseModel):
    provider:      str = "oidc"
    client_id:     str
    client_secret: str
    discovery_url: str | None = None


class SSOConfigResponse(BaseModel):
    id:            str
    provider:      str
    client_id:     str
    discovery_url: str | None
    enabled:       bool
    created_at:    str


@router.get("/sso/config", response_model=list[SSOConfigResponse])
async def list_sso_configs(
    pool: asyncpg.Pool = Depends(get_pool),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """List SSO configurations for the authenticated org (admin only)."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    org_id = verify_jwt_get_org_id(credentials.credentials)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            rows = await conn.fetch(
                """
                SELECT id::text, provider, client_id, discovery_url, enabled,
                       created_at::text
                FROM   sso_configs
                WHERE  org_id = $1
                ORDER  BY created_at
                """,
                org_id,
            )
    return [dict(r) for r in rows]


@router.post("/sso/config", response_model=SSOConfigResponse, status_code=201)
async def create_sso_config(
    body: SSOConfigRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """Create or replace an SSO config for the authenticated org (admin only)."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    org_id = verify_jwt_get_org_id(credentials.credentials)

    if body.provider == "oidc" and not body.discovery_url:
        raise HTTPException(status_code=400, detail="discovery_url is required for oidc provider")

    # Validate discovery URL (SSRF guard + reachability check)
    if body.discovery_url:
        # Raises HTTPException with specific message if URL is invalid/internal
        _validate_discovery_url(f"{body.discovery_url.rstrip('/')}/.well-known/openid-configuration")
        try:
            await _get_discovery(body.discovery_url)
        except HTTPException:
            raise   # propagate SSRF / validation errors as-is
        except Exception:
            raise HTTPException(
                status_code=400,
                detail=f"Could not reach OIDC discovery endpoint: {body.discovery_url}/.well-known/openid-configuration",
            )

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            row = await conn.fetchrow(
                """
                INSERT INTO sso_configs (org_id, provider, client_id, client_secret, discovery_url)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (org_id, provider) DO UPDATE
                  SET client_id     = EXCLUDED.client_id,
                      client_secret = EXCLUDED.client_secret,
                      discovery_url = EXCLUDED.discovery_url,
                      updated_at    = NOW(),
                      enabled       = TRUE
                RETURNING id::text, provider, client_id, discovery_url, enabled, created_at::text
                """,
                org_id, body.provider, body.client_id, body.client_secret, body.discovery_url,
            )
    return dict(row)


@router.delete("/sso/config/{provider}", status_code=204)
async def delete_sso_config(
    provider: str,
    pool: asyncpg.Pool = Depends(get_pool),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """Delete an SSO config (admin only)."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    org_id = verify_jwt_get_org_id(credentials.credentials)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE app_role")
            await conn.execute(f"SET LOCAL app.org_id = '{org_id}'")
            deleted = await conn.fetchval(
                "DELETE FROM sso_configs WHERE org_id = $1 AND provider = $2 RETURNING id",
                org_id, provider,
            )
    if deleted is None:
        raise HTTPException(status_code=404, detail="SSO config not found")

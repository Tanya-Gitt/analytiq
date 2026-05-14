<div align="center">

<h1>📊 Analytiq</h1>

<p><strong>The self-hostable product analytics platform you actually own.</strong><br/>
Event tracking · E-commerce analytics · Feature flags · AI Copilot — in a single Docker Compose stack.<br/>
No SaaS fees. No data leaving your servers. One command to run.</p>

[![CI](https://github.com/Tanya-Gitt/analytiq/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Tanya-Gitt/analytiq/actions)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ed?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose)

</div>

---

## Why Analytiq?

| | Analytiq | Segment / Mixpanel | Self-hosted Matomo |
|---|---|---|---|
| **Data ownership** | ✅ 100% yours | ❌ third-party servers | ✅ |
| **Multi-tenant RLS** | ✅ Postgres row-level security | ❌ | ❌ |
| **Events + E-commerce** | ✅ both in one platform | events only | events only |
| **Feature flags + A/B** | ✅ built-in, with SDK | ❌ (paid add-on) | ❌ |
| **AI Copilot** | ✅ natural language → SQL | ❌ | ❌ |
| **Alerting built-in** | ✅ Slack + email | ❌ (paid add-on) | limited |
| **SSO / OIDC** | ✅ Google, GitHub, any OIDC | ❌ (enterprise tier) | paid |
| **GDPR tools** | ✅ forget + export + opt-out | manual | basic |
| **Monthly cost** | ✅ $0 (+ your server) | 💸 $120+/mo | free |
| **One-command deploy** | ✅ `docker compose up` | ❌ | complex |

---

## ✨ Feature Overview

<details open>
<summary><strong>📈 Analytics &amp; Dashboards</strong></summary>

**Segment A — Event analytics**
- Browser JS SDK with `identify`, `track`, and `page` calls
- Events timeline, top events, new vs returning users chart
- Per-event-type filtering with 7 / 30 / 90-day windows
- **Retention cohort heatmap** — weekly cohort table, color-coded drop-off

**Segment B — E-commerce analytics**
- Revenue trend, AOV trend, top products, top channels (donut), revenue by region
- Period-over-period comparison badges (vs previous window)
- Per-channel filtering, delivery rate KPI
- Orders via webhook, CSV upload, or Google Sheets polling

</details>

<details>
<summary><strong>🚩 Feature Flags &amp; A/B Experimentation</strong></summary>

- Create, toggle, and delete feature flags from the dashboard
- Gradual rollout — set rollout % (0 – 100%) with consistent user hashing
- Targeting rules — per-attribute targeting (plan, country, user ID, etc.)
- Server-side evaluation API: `POST /api/flags/evaluate` with `user_id` + attributes
- All flag mutations written to the audit log
- Real-time toggle with optimistic UI updates

```python
# Server-side flag evaluation
import httpx
flags = httpx.post(
    "https://your-host/api/flags/evaluate",
    headers={"Authorization": "Bearer YOUR_JWT"},
    json={"user_id": "u_123", "attributes": {"plan": "pro", "country": "US"}},
).json()
# → {"new-checkout-flow": True, "dark-mode": False, ...}
```

</details>

<details>
<summary><strong>🤖 AI Product Copilot</strong></summary>

- Natural-language question → validated SQL → chart + insight, all in one click
- Powered by Groq (swap any OpenAI-compatible endpoint)
- Auto-generates chart type, axis keys, and a plain-English insight
- SQL whitelist: only `SELECT` statements execute — no writes, no schema leaks
- All queries run inside a read-only RLS transaction (sees only your org's data)
- Suggested questions tailored to your actual data shape

</details>

<details>
<summary><strong>🔔 Smart Alerting</strong></summary>

- Define rules on any metric: `total_revenue`, `total_events`, `delivery_rate`, `no_data`
- Conditions: `above` / `below` threshold, or `no_data` in a window
- Alert FSM: OK → TRIGGERED → OK with auto-resolve and 24h re-notify
- Notifications via Slack webhook or SMTP email

</details>

<details>
<summary><strong>👥 People &amp; User Profiles</strong></summary>

- Paginated list of all identified users with searchable traits
- Single-user drill-down: full trait history + event timeline
- Churn prediction: users scored by days since last seen → risk levels (healthy / warning / at-risk / critical)

</details>

<details>
<summary><strong>🗺️ Path Analysis</strong></summary>

- Discover the top N event sequences users actually follow after a starting event
- Sankey-style path visualization
- Configurable depth and date window

</details>

<details>
<summary><strong>⚡ Anomaly Detection</strong></summary>

- Automated Z-score detection on hourly metrics (events count, revenue)
- Learns baselines by day-of-week × hour-of-day
- Anomaly events stored and queryable; admin backfill endpoint
- Visualized in the dashboard with alert integration

</details>

<details>
<summary><strong>🔑 Scoped API Keys</strong></summary>

- Create named API keys with granular scopes: `ingest`, `read`, `admin`
- Optional expiry (30d / 90d / 1yr / never)
- Full key shown **once** at creation — only the prefix is stored after that
- Revoke instantly; revoked keys are rejected at the middleware layer

</details>

<details>
<summary><strong>🔒 GDPR / CCPA Compliance</strong></summary>

- **Right to access** — export all data for a user in one API call
- **Right to be forgotten** — erase all events, orders, and traits for a user
- **Opt-out management** — opt users out of tracking; SDK respects opt-out list
- All GDPR actions written to the audit log with actor + timestamp

</details>

<details>
<summary><strong>📋 Audit Log</strong></summary>

- Immutable, append-only log of every admin action
- Covers: flags, team, connectors, GDPR, alerts, API keys, embed tokens
- Filterable by category; paginated with up to 500 results per page
- Actor email + IP address + timestamp on every entry

</details>

<details>
<summary><strong>🔗 Custom Funnels</strong></summary>

- Build any multi-step user journey (up to 10 steps) with a drag-and-drop editor
- Event name autocomplete from your live data
- Ordered funnel algorithm: step N only counts users who completed all prior steps
- 7 / 14 / 30 / 90-day windows, live chart with drop-off visualization

</details>

<details>
<summary><strong>📤 Sharing &amp; Embed</strong></summary>

- **Share links** — share a read-only dashboard snapshot (Segment A or B) with anyone, no login required; optional expiry date; revoke at any time
- **Embedded analytics** — generate embed tokens scoped to specific widgets; serve charts on external sites via a public read-only endpoint
- **Chart annotations** — pin notes to specific dates on time-series charts; color-coded reference lines

</details>

<details>
<summary><strong>📦 Warehouse &amp; Storage</strong></summary>

- **Bulk export** — download events, orders, or user profiles as JSON or CSV
- **Tiered storage** — archive events older than N days to `archived_events` table; query archived data separately to keep hot storage fast
- Storage stats: hot vs archived row counts with size estimates

</details>

<details>
<summary><strong>📅 Scheduled Reports</strong></summary>

- Create recurring reports for any metric (events count, revenue, DAU, churn, etc.)
- Daily / weekly / monthly cadence
- Delivered by email to a configurable list of recipients
- Run immediately on demand

</details>

<details>
<summary><strong>👨‍👩‍👧 Team &amp; SSO</strong></summary>

- Invite teammates by email — shareable token link with 7-day expiry
- Roles: `admin` (full control) and `viewer` (read-only dashboards)
- **SSO / OAuth 2.0 / OIDC** — Google and GitHub out of the box; any OIDC-compliant provider (Okta, Azure AD, Keycloak, Auth0) via per-org config
- JIT (just-in-time) user provisioning on first SSO login
- JWT role claims enforced at the API layer on every request

</details>

---

## 🔐 Security — Defence in Depth

Analytiq was built with the assumption that it handles sensitive product data. Security is not a checkbox — it's layered throughout the stack.

### Authentication & Access Control

| Layer | Mechanism |
|---|---|
| **Multi-tenant isolation** | Postgres RLS + `SET LOCAL app.org_id` — enforced at the DB layer, not the app layer. A misconfigured route cannot leak another org's data. |
| **Password policy** | Minimum 12 characters, uppercase + lowercase + digit required. Checked against 5 known common passwords. |
| **Have I Been Pwned** | Every new password is checked via HIBP's k-anonymity API (only the first 5 SHA-1 hex chars leave the server). Breached passwords are rejected. |
| **Account lockout** | 10 consecutive failed logins lock the account for 15 minutes. Constant-time bcrypt dummy hash prevents user enumeration via timing attacks. |
| **JWT hardening** | HS256, 24-hour expiry, secret from env — never hardcoded. UUID org_id claim validated on every request. |
| **SSO state forgery** | Cryptographic `state` parameter stored in DB and verified on OAuth callback — prevents CSRF in the OAuth flow. |

### Network & Transport

| Layer | Mechanism |
|---|---|
| **Brute-force rate limiting** | nginx rate-limits `/api/auth/login`, `/api/auth/signup`, and `/auth/token` to **5 req/min per IP** before the request reaches the app. |
| **API rate limiting** | 100 req/s token-bucket per org, Postgres-backed — survives restarts and horizontal scaling. |
| **Security headers** | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin`, `Permissions-Policy: geolocation=(), camera=(), microphone=()` |
| **Content Security Policy** | Strict CSP on all responses — restricts scripts, styles, frames, form targets, and object sources. |
| **Clickjacking** | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` — belt and braces. |

### Data & API Security

| Layer | Mechanism |
|---|---|
| **Webhook authenticity** | HMAC-SHA256 signature verified with `hmac.compare_digest()` (timing-safe); 1 MB payload cap. |
| **SQL injection** | `sanitize_column_name()` strips all non-`[a-zA-Z0-9_]` chars before any dynamic DDL. All queries use parameterized `$1` placeholders. |
| **CSV safety** | 10 MB hard cap enforced before and after read; column names sanitized before any DDL; no path traversal. |
| **AI Copilot SQL** | Generated SQL is validated to be `SELECT`-only before execution. Row cap: max 500 rows. Postgres errors are sanitized before being returned (no schema leaks). |
| **Scoped API keys** | Keys use `ingest` / `read` / `admin` scopes; bcrypt-hashed in the DB; only prefix stored after creation. |

### UX-Level Security

| Layer | Mechanism |
|---|---|
| **Type-to-confirm dialogs** | All irreversible destructive actions (delete flag, revoke API key, forget user, etc.) require the user to physically type the action word (e.g. `delete`, `revoke`, `logout`) before the button enables. Paste and drag-drop are blocked; whitespace is stripped to prevent browser auto-space bypass. |
| **Logout confirmation** | Users must type `logout` to confirm — prevents accidental session termination and tab-jacking attacks that trigger logout links. |

### Supply Chain & Runtime

| Layer | Mechanism |
|---|---|
| **Pinned Actions** | All GitHub Actions use SHA-pinned references (not mutable version tags) — immune to tag-poisoning supply-chain attacks. |
| **Non-root containers** | Both `app` and `scheduler` run as `appuser` (uid 1001) — a compromised process cannot write to system paths. |
| **Env secrets only** | No credentials in code or Docker images. All secrets are injected at runtime via `.env`. |

> ⚠️ **Never call `pool.acquire()` directly in route handlers.** Always use `get_org_db` from `app/deps.py` — it sets `app.org_id` inside a transaction so RLS is enforced on every query.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Stack                          │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  nginx :80                                                     │   │
│  │  /api/*  →  FastAPI :8000      /*  →  Next.js :3000           │   │
│  │  /sdk/*  →  FastAPI :8000      /auth/*  →  GoTrue :9999       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│            │                                │                         │
│     ┌──────▼──────┐                 ┌───────▼──────┐                │
│     │  FastAPI    │                 │   Next.js    │                 │
│     │  :8000      │                 │   :3000      │                 │
│     │  REST API   │                 │   Dashboard  │                 │
│     │  RLS auth   │                 │   UI         │                 │
│     │  Rate limit │                 │   Recharts   │                 │
│     └──────┬──────┘                 └──────────────┘                │
│            │                                                          │
│     ┌──────▼──────────────────────────────────────────────────┐     │
│     │  PostgreSQL :5432  (Row-Level Security, 30+ tables)      │     │
│     │  orgs · users · events · orders · connectors             │     │
│     │  alert_rules · sync_runs · share_tokens · annotations    │     │
│     │  org_invites · funnels · feature_flags · api_keys        │     │
│     │  audit_log · gdpr_opt_outs · churn_scores · anomalies    │     │
│     │  embed_tokens · sso_configs · scheduled_reports          │     │
│     └─────────────────────────────────────────────────────────┘     │
│            │                                                          │
│     ┌──────▼──────┐                                                  │
│     │ APScheduler │  connector polling (60s) · alert eval (60s)      │
│     │ :scheduler  │  anomaly detection · orphan recovery (5m)        │
│     └─────────────┘                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

**Six containers:** `postgres` · `app` (FastAPI) · `frontend` (Next.js) · `scheduler` · `auth` (GoTrue) · `nginx`

---

## 🚀 Quickstart

### Prerequisites

- Docker + Docker Compose v2
- 1 GB RAM minimum; any Linux / macOS / Windows with WSL2

### 1 — Clone and configure

```bash
git clone https://github.com/Tanya-Gitt/analytiq.git
cd analytiq
cp .env.example .env
```

Open `.env` and fill in the two required values:

```bash
POSTGRES_PASSWORD=a_strong_random_password
JWT_SECRET=at_least_32_random_chars
# Generate one: python -c "import secrets; print(secrets.token_hex(32))"
```

### 2 — Start the stack

```bash
docker compose up --build
```

First boot takes ~60 seconds while Postgres initialises. When you see `app | Application startup complete`, open **http://localhost** and create your workspace.

### 3 — Set a strong password

The signup form enforces the password policy: **12+ characters, uppercase, lowercase, digit**. Passwords found in data breaches are rejected automatically via HIBP.

---

## 📥 Ingestion Methods

### A · JavaScript SDK (browser events)

```html
<script src="http://localhost/sdk/analytics.js"></script>
<script>
  Analytics.init('YOUR_ORG_API_KEY', { host: 'http://localhost' });
  Analytics.identify('user-123', { plan: 'pro', country: 'US' });
  Analytics.track('Purchase', { sku: 'PROD-42', price: 29.99 });
  Analytics.page(); // auto-tracks page views
</script>
```

Create a `js_sdk` connector first to allowlist your origin.

### B · Webhook (real-time orders / events)

```bash
# Create a webhook connector
curl -X POST http://localhost/api/connectors \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"type":"webhook","segment":"B","config":{"secret":"your-hmac-secret"}}'

# Send an HMAC-signed order
BODY='{"order_id":"ORD-1","order_date":"2024-03-15","quantity":2,"price_per_unit":49.99}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "your-hmac-secret" | awk '{print $2}')
curl -X POST http://localhost/api/webhook/$CONNECTOR_ID \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: $SIG" \
  -d "$BODY"
```

### C · CSV Upload (drag-and-drop)

Go to **Connectors → Add connector → CSV Upload**, map your column headers, and upload. Sync runs immediately.

### D · Google Sheets (scheduled pull)

Publish your Sheet as CSV (**File → Share → Publish to web → CSV format**), create a `sheets_csv` connector with the URL, and the scheduler polls it every 60 seconds.

---

## 🔑 API Keys

Generate scoped keys for programmatic access without sharing your JWT:

```bash
# Create an ingest-only key
curl -X POST http://localhost/api/api-keys \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"Production Ingest","scopes":["ingest"],"expires_days":90}'

# Use it to send events
curl -X POST http://localhost/api/ingest \
  -H "X-API-Key: ak_prod_..." \
  -d '{"event":"page_view","user_id":"u_123"}'
```

Available scopes:

| Scope | Grants |
|---|---|
| `ingest` | Write events and orders only |
| `read` | Query dashboards, people, flags |
| `admin` | Full API access (same as JWT) |

---

## 🚩 Feature Flags

```python
# Python — server-side evaluation
import httpx

flags = httpx.post(
    "https://your-host/api/flags/evaluate",
    headers={"Authorization": "Bearer YOUR_JWT"},
    json={
        "user_id": "u_123",
        "attributes": {"plan": "pro", "country": "US"},
    },
).json()

if flags.get("new-checkout-flow"):
    show_new_checkout()
```

```js
// JavaScript — same endpoint, same result
const flags = await fetch('/api/flags/evaluate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
  body: JSON.stringify({ user_id: userId, attributes: { plan: 'pro' } }),
}).then(r => r.json());
```

Targeting rules support any attribute: `plan`, `country`, `beta_user`, user ID allowlists, and more.

---

## 🤖 AI Copilot

Ask questions in plain English — the Copilot generates SQL, validates it, runs it against your data, and returns a chart + insight:

> *"Which channels drove the most revenue last 30 days?"*
> *"Show me the signup funnel drop-off by country"*
> *"How many users became active in Q1 and churned in Q2?"*

Set `GROQ_API_KEY` in `.env` to activate. Works with any OpenAI-compatible endpoint — swap `GROQ_API_URL` for a local model.

---

## 🧪 Running Tests

```bash
# One-time: create the test database
createdb analytics_test

# Install dev deps
pip install -r requirements-dev.txt

# Run full suite
pytest tests/ -v --tb=short
```

Tests hit a **real Postgres instance** — no mocks for the database layer. Every assertion is against actual SQL output.

```
✓  backend tests pass (real Postgres, no mocks)
✓  ruff linting clean
✓  mypy type checks pass
✓  Next.js TypeScript build passes
✓  Docker Compose smoke test (signup → login → dashboard → SDK file)
```

---

## 📁 Project Structure

```
analytiq/
├── app/
│   ├── routers/
│   │   ├── auth.py              # Signup, login, /me — password policy + HIBP
│   │   ├── sso.py               # Google / GitHub / OIDC SSO with JIT provisioning
│   │   ├── api_keys.py          # Scoped API key CRUD
│   │   ├── flags.py             # Feature flags + A/B evaluation endpoint
│   │   ├── dashboard.py         # Segment A + B dashboard queries
│   │   ├── connectors.py        # Connector CRUD, sync trigger, CSV upload
│   │   ├── ingest.py            # JS SDK ingest + rate limiter
│   │   ├── webhook.py           # HMAC-verified webhook receiver
│   │   ├── alerts.py            # Alert rule CRUD
│   │   ├── anomalies.py         # Anomaly detection + baseline management
│   │   ├── people.py            # User profiles + trait history
│   │   ├── churn.py             # Churn prediction + risk scoring
│   │   ├── paths.py             # Path / flow analysis
│   │   ├── funnels.py           # Custom funnel builder + query
│   │   ├── copilot.py           # AI Copilot — NL → SQL → chart
│   │   ├── share.py             # Public share token CRUD + data endpoint
│   │   ├── embed.py             # Embed token CRUD + public widget endpoint
│   │   ├── annotations.py       # Chart annotation CRUD
│   │   ├── team.py              # Team invites + member management
│   │   ├── gdpr.py              # GDPR forget / export / opt-out
│   │   ├── audit.py             # Audit log query
│   │   ├── reports.py           # Scheduled custom reports
│   │   ├── warehouse.py         # Bulk data export (events / orders / users)
│   │   ├── storage.py           # Tiered storage — archive + query archived events
│   │   ├── heatmaps.py          # Retention cohort heatmap
│   │   ├── export.py            # CSV download endpoint
│   │   ├── stream.py            # SSE real-time event feed
│   │   └── system.py            # Health check + system info
│   ├── audit_log.py             # Append-only audit log helper
│   ├── deps.py                  # RLS dependency injection — always use this!
│   └── auth.py                  # JWT utilities (create, verify, role claims)
│
├── scheduler/
│   ├── main.py                  # APScheduler polling loop
│   ├── metrics.py               # Metric evaluation + anomaly detection
│   ├── alert_evaluator.py       # Alert FSM (OK ↔ TRIGGERED)
│   └── notifications.py         # SMTP + Slack notification helpers
│
├── frontend/src/app/
│   ├── dashboard/               # Segment A + B dashboards (tabs)
│   ├── flags/                   # Feature flag management
│   ├── api-keys/                # API key management
│   ├── people/                  # User profile list + detail
│   ├── paths/                   # Path analysis visualization
│   ├── anomalies/               # Anomaly feed + baselines
│   ├── churn/                   # Churn risk dashboard
│   ├── funnels/                 # Drag-and-drop funnel builder
│   ├── alerts/                  # Alert rule management
│   ├── audit/                   # Audit log browser
│   ├── gdpr/                    # GDPR tools (forget / export / opt-out)
│   ├── connectors/              # Connector management
│   ├── embed/                   # Embed token management
│   ├── storage/                 # Storage stats + archive controls
│   ├── reports/                 # Scheduled report management
│   ├── warehouse/               # Bulk export UI
│   ├── live/                    # Real-time SSE event feed
│   ├── share/[token]/           # Public shared dashboard
│   └── invite/[token]/          # Accept-invite public page
│
├── frontend/src/components/
│   ├── ConfirmDialog.tsx         # Type-to-confirm security dialog (portal-based)
│   ├── ShareModal.tsx            # Share link management modal
│   └── layout/                  # AppShell, Sidebar, nav
│
├── sdk/
│   └── analytics.js             # Browser JS SDK (identify, track, page)
├── db/
│   └── schema.sql               # Core PostgreSQL schema + RLS policies
├── nginx/
│   └── default.conf             # Reverse proxy + rate limiting + security headers
├── tests/                       # pytest tests — real Postgres, no DB mocks
├── docker-compose.yml           # Full 6-container stack
└── .env.example                 # Copy → .env, fill 2 values, done
```

---

## ⚙️ Environment Variables

| Variable | Required | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | ✅ | PostgreSQL password |
| `JWT_SECRET` | ✅ | JWT signing secret (≥ 32 chars) |
| `GROQ_API_KEY` | optional | Enables the AI Copilot |
| `GROQ_API_URL` | optional | Custom OpenAI-compatible endpoint (default: Groq) |
| `GOOGLE_CLIENT_ID` | optional | Google OAuth SSO |
| `GOOGLE_CLIENT_SECRET` | optional | Google OAuth SSO |
| `GITHUB_CLIENT_ID` | optional | GitHub OAuth SSO |
| `GITHUB_CLIENT_SECRET` | optional | GitHub OAuth SSO |
| `APP_BASE_URL` | optional | Public URL for SSO callbacks (e.g. `https://analytics.example.com`) |
| `SMTP_HOST` | optional | SMTP server for email alerts + reports |
| `SMTP_PORT` | optional | SMTP port (default: 587) |
| `SMTP_USER` | optional | SMTP username |
| `SMTP_PASS` | optional | SMTP password |
| `SMTP_FROM` | optional | Sender address |
| `SLACK_WEBHOOK_URL` | optional | Slack incoming webhook for alerts |

---

## 🤝 Contributing

Pull requests are welcome. For major changes, open an issue first.

```bash
# Full quality gate — must be green before submitting
ruff check app/ scheduler/ tests/ --select E,F,W,I --ignore E501
mypy app/ scheduler/ --ignore-missing-imports --no-strict-optional
pytest tests/ -q
```

---

## 📄 License

AGPL v3 — free for open-source use. Commercial use requires a license. See [LICENSE](LICENSE) or contact purusharth2021@gmail.com.

---

<div align="center">
<sub>Built with FastAPI · Next.js · PostgreSQL · APScheduler · Docker</sub>
</div>

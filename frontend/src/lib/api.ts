/**
 * Typed API client for the FastAPI backend.
 * All requests go through /api/* (proxied by nginx → app:8000).
 */

import { authHeader } from './auth';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';

// ── helpers ─────────────────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeader(),
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = body?.detail ?? `HTTP ${res.status}`;
    // Auto-redirect to login on 401 (expired/invalid token)
    // This prevents the "invalid or expired token" error from showing on the dashboard.
    if (res.status === 401 && typeof window !== 'undefined') {
      // Clear stale auth data and redirect to login
      localStorage.removeItem('analytics_jwt');
      localStorage.removeItem('analytics_api_key');
      localStorage.removeItem('analytics_org_id');
      window.location.replace('/login');
    }
    throw new ApiError(res.status, msg);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface AuthResponse {
  access_token: string;
  api_key: string;
  org_id: string;
}

export function signup(email: string, password: string, orgName: string) {
  return request<AuthResponse>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email, password, org_name: orgName }),
  });
}

export function login(email: string, password: string) {
  return request<AuthResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

// ── Dashboard — Segment B ─────────────────────────────────────────────────────

export interface RevenueTrendPoint { date: string; revenue: number }
export interface TopChannel { channel: string; revenue: number }
export interface TopProduct { product_name: string; revenue: number; units_sold: number }
export interface AovTrendPoint { date: string; aov: number }
export interface RevenueByRegion { region: string; revenue: number }
export interface SegmentBDashboard {
  revenue_trend: RevenueTrendPoint[];
  top_channels: TopChannel[];
  top_products: TopProduct[];
  aov_trend: AovTrendPoint[];
  revenue_by_region: RevenueByRegion[];
  delivery_rate: number | null;
  total_orders: number;
  total_revenue: number;
  prev_total_orders: number;
  prev_total_revenue: number;
  available_channels: string[];
}

export function getSegmentBDashboard(days = 30, channel?: string) {
  const params = new URLSearchParams({ days: String(days) });
  if (channel) params.set('channel', channel);
  return request<SegmentBDashboard>(`/dashboard/segment-b?${params}`);
}

// ── Dashboard — Segment A ─────────────────────────────────────────────────────

export interface EventsTimelinePoint { date: string; count: number }
export interface TopEvent { event_name: string; count: number }
export interface FunnelStep { step: string; users: number }
export interface NewVsReturningPoint { date: string; new_users: number; returning_users: number }
export interface SegmentADashboard {
  events_timeline: EventsTimelinePoint[];
  top_events: TopEvent[];
  funnel: FunnelStep[];
  new_vs_returning: NewVsReturningPoint[];
  dau: number | null;
  total_events: number;
  prev_total_events: number;
  available_event_types: string[];
}

export function getSegmentADashboard(days = 30, eventType?: string) {
  const params = new URLSearchParams({ days: String(days) });
  if (eventType) params.set('event_type', eventType);
  return request<SegmentADashboard>(`/dashboard/segment-a?${params}`);
}

// ── Connectors ────────────────────────────────────────────────────────────────

export interface Connector {
  id: string;
  name: string;
  type: 'sheets_csv' | 'csv_upload' | 'webhook' | 'js_sdk';
  segment: 'A' | 'B';
  status: 'active' | 'error' | 'paused';
  sync_interval_minutes: number;
  last_synced_at: string | null;
  last_error: string | null;
  created_at: string;
}

export function listConnectors() {
  return request<Connector[]>('/connectors');
}

export function createConnector(payload: {
  type: string;
  segment: string;
  name?: string;
  config?: Record<string, unknown>;
  sync_interval_minutes?: number;
}) {
  return request<Connector>('/connectors', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export interface SyncRun {
  id: number;
  status: 'running' | 'success' | 'failed';
  started_at: string;
  finished_at: string | null;
  rows_upserted: number | null;
  error_message: string | null;
}

export function getSyncRuns(connectorId: string) {
  return request<SyncRun[]>(`/connectors/${connectorId}/sync-runs`);
}

export function deleteConnector(connectorId: string) {
  return request<void>(`/connectors/${connectorId}`, { method: 'DELETE' });
}

export function triggerSync(connectorId: string) {
  return request<{ ok: boolean; message: string }>(
    `/connectors/${connectorId}/sync`,
    { method: 'POST' },
  );
}

export interface UploadCsvResponse {
  ok: boolean;
  message: string;
}

/**
 * Upload a CSV file to a csv_upload connector and trigger an immediate sync.
 * Returns 202 Accepted — the sync runs asynchronously.
 *
 * Uses a raw fetch instead of `request()` because `request()` sets
 * Content-Type: application/json which would break multipart/form-data.
 * fetch() sets the correct boundary automatically when given a FormData body.
 */
export async function uploadCsv(
  connectorId: string,
  file: File,
): Promise<UploadCsvResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/connectors/${connectorId}/upload-csv`, {
    method: 'POST',
    headers: { ...authHeader() },  // no Content-Type — let fetch set it
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = (body?.detail as string) ?? `HTTP ${res.status}`;
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<UploadCsvResponse>;
}

// ── Alert Rules ───────────────────────────────────────────────────────────────

export interface AlertRule {
  id: string;
  name: string;
  metric: string;
  condition: 'below' | 'above' | 'no_data';
  threshold: number | null;
  window_hours: number;
  channel: 'slack' | 'email';
  destination: string;
  state: 'OK' | 'TRIGGERED';
  last_triggered_at: string | null;
  created_at: string;
}

export function listAlertRules() {
  return request<AlertRule[]>('/alerts');
}

export function createAlertRule(payload: {
  name: string;
  metric: string;
  condition: string;
  threshold?: number;
  window_hours?: number;
  channel: string;
  destination: string;
}) {
  return request<AlertRule>('/alerts', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteAlertRule(id: string) {
  return request<void>(`/alerts/${id}`, { method: 'DELETE' });
}

// ── Auth: settings ────────────────────────────────────────────────────────────

export interface MeResponse {
  user_id: string;
  email: string;
  org_name: string;
  api_key: string;
}

export function getMe() {
  return request<MeResponse>('/auth/me');
}

export function rotateApiKey() {
  return request<{ api_key: string }>('/auth/rotate-api-key', { method: 'POST' });
}

// ── Connectors: update ────────────────────────────────────────────────────────

export function updateConnector(
  connectorId: string,
  patch: { name?: string; sync_interval_minutes?: number; status?: string },
) {
  return request<Connector>(`/connectors/${connectorId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

// ── Dashboard — Retention cohort ─────────────────────────────────────────────

export interface RetentionWeek    { week_number: number; retained: number }
export interface RetentionCohort  {
  cohort_week:  string;
  cohort_size:  number;
  weeks:        RetentionWeek[];
}
export interface AvgByWeek { week_number: number; avg_pct: number }
export interface RetentionData {
  cohorts:            RetentionCohort[];
  weeks:              number;
  avg_by_week:        AvgByWeek[];
  dau:                number;
  wau:                number;
  mau:                number;
  stickiness_dau_wau: number | null;
  stickiness_dau_mau: number | null;
}

export function getRetention(weeks = 12) {
  return request<RetentionData>(`/dashboard/retention?weeks=${weeks}`);
}

// ── Share tokens ──────────────────────────────────────────────────────────────

export interface ShareToken {
  id: string;
  token: string;
  segment: 'A' | 'B';
  days: number;
  label: string;
  expires_at: string | null;
  created_at: string;
  public_url: string;
}

export function listShareTokens() {
  return request<ShareToken[]>('/share');
}

export function createShareToken(payload: {
  segment: 'A' | 'B';
  days?: number;
  label?: string;
  expires_at?: string | null;
}) {
  return request<ShareToken>('/share', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function revokeShareToken(token: string) {
  return request<void>(`/share/${token}`, { method: 'DELETE' });
}

/** Public — no auth header needed */
export function getShareData(token: string) {
  return fetch(`${BASE}/share/${token}/data`).then(async (res) => {
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body?.detail ?? `HTTP ${res.status}`);
    }
    return res.json();
  });
}

// ── Annotations ───────────────────────────────────────────────────────────────

export interface Annotation {
  id: string;
  segment: 'A' | 'B';
  date: string;
  label: string;
  color: string;
  created_at: string;
}

export function listAnnotations(segment: 'A' | 'B') {
  return request<Annotation[]>(`/annotations?segment=${segment}`);
}

export function createAnnotation(payload: {
  segment: 'A' | 'B';
  date: string;
  label: string;
  color?: string;
}) {
  return request<Annotation>('/annotations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteAnnotation(id: string) {
  return request<void>(`/annotations/${id}`, { method: 'DELETE' });
}

// ── Export ────────────────────────────────────────────────────────────────────

/**
 * Trigger a CSV export download by creating a hidden <a> element.
 * The Authorization header cannot be set on a plain browser download, so we
 * fetch it via XHR and create an object URL instead.
 */
export async function downloadExport(
  segment: 'segment-a' | 'segment-b',
  days: number,
  filter?: { channel?: string; event_type?: string },
): Promise<void> {
  const params = new URLSearchParams({ days: String(days) });
  if (filter?.channel)    params.set('channel',    filter.channel);
  if (filter?.event_type) params.set('event_type', filter.event_type);

  const res = await fetch(`${BASE}/export/${segment}?${params}`, {
    headers: authHeader(),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body?.detail ?? `HTTP ${res.status}`);
  }

  const blob = await res.blob();
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  const cd   = res.headers.get('content-disposition') ?? '';
  const name = cd.match(/filename="([^"]+)"/)?.[1] ?? `${segment}_${days}d.csv`;
  a.href     = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Team management ───────────────────────────────────────────────────────────

export interface TeamMember {
  id: string;
  email: string;
  role: 'admin' | 'viewer';
  created_at: string;
}

export interface PendingInvite {
  id: string;
  email: string;
  role: 'admin' | 'viewer';
  expires_at: string;
  created_at: string;
}

export interface TeamResponse {
  members: TeamMember[];
  pending_invites: PendingInvite[];
}

export function getTeam() {
  return request<TeamResponse>('/team/members');
}

export function inviteMember(email: string, role: 'admin' | 'viewer' = 'viewer') {
  return request<{ id: string; email: string; role: string; invite_url: string }>(
    '/team/invite',
    { method: 'POST', body: JSON.stringify({ email, role }) },
  );
}

export function removeMember(userId: string) {
  return request<void>(`/team/members/${userId}`, { method: 'DELETE' });
}

export function updateMemberRole(userId: string, role: 'admin' | 'viewer') {
  return request<TeamMember>(`/team/members/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  });
}

export function cancelInvite(inviteId: string) {
  return request<void>(`/team/invites/${inviteId}`, { method: 'DELETE' });
}

/** Public — no auth */
export function getInvite(token: string) {
  return fetch(`${BASE}/invite/${token}`).then(async (res) => {
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body?.detail ?? `HTTP ${res.status}`);
    }
    return res.json() as Promise<{ id: string; email: string; role: string; org_name: string }>;
  });
}

/** Public — no auth */
export function acceptInvite(token: string, password: string) {
  return fetch(`${BASE}/invite/${token}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  }).then(async (res) => {
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body?.detail ?? `HTTP ${res.status}`);
    }
    return res.json() as Promise<{ access_token: string; org_id: string }>;
  });
}

// ── SSO config ────────────────────────────────────────────────────────────────

export interface SSOConfig {
  id:            string;
  provider:      string;
  client_id:     string;
  discovery_url: string | null;
  enabled:       boolean;
  created_at:    string;
}

export function listSSOConfigs() {
  return request<SSOConfig[]>('/auth/sso/config');
}

export function createSSOConfig(payload: {
  provider: string;
  client_id: string;
  client_secret: string;
  discovery_url?: string;
}) {
  return request<SSOConfig>('/auth/sso/config', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteSSOConfig(provider: string) {
  return request<void>(`/auth/sso/config/${provider}`, { method: 'DELETE' });
}

// ── Custom funnels ────────────────────────────────────────────────────────────

export interface Funnel {
  id: string;
  name: string;
  steps: string[];
  created_at: string;
  updated_at: string;
}

export interface FunnelStep {
  step: string;
  users: number;
}

export interface FunnelData {
  funnel_id: string;
  name: string;
  steps: FunnelStep[];
  days: number;
}

export function listFunnels() {
  return request<Funnel[]>('/funnels');
}

export function createFunnel(name: string, steps: string[]) {
  return request<Funnel>('/funnels', {
    method: 'POST',
    body: JSON.stringify({ name, steps }),
  });
}

export function updateFunnel(id: string, patch: { name?: string; steps?: string[] }) {
  return request<Funnel>(`/funnels/${id}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export function deleteFunnel(id: string) {
  return request<void>(`/funnels/${id}`, { method: 'DELETE' });
}

export function getFunnelData(id: string, days = 30) {
  return request<FunnelData>(`/funnels/${id}/data?days=${days}`);
}

export function listFunnelEvents() {
  return request<string[]>('/funnels/events');
}

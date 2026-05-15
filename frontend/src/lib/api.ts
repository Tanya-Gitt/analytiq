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
  const url = `${BASE}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...authHeader(),
        ...(options.headers ?? {}),
      },
    });
  } catch (e: unknown) {
    throw new Error(`[${url}] ${e instanceof Error ? e.message : String(e)}`);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body?.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ')
      : (detail ?? `HTTP ${res.status}`);
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

// ── Anomaly Detection ─────────────────────────────────────────────────────────

export interface AnomalyEvent {
  id:          number;
  metric:      string;
  value:       number;
  baseline:    number;
  std_dev:     number;
  z_score:     number;
  direction:   'high' | 'low';
  severity:    'warning' | 'critical';
  detected_at: string;
}

export interface AnomalySummary {
  last_24h:    number;
  last_7d:     number;
  critical_24h: number;
  warning_24h:  number;
}

export function listAnomalies(metric?: string, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (metric) params.set('metric', metric);
  return request<AnomalyEvent[]>(`/anomalies?${params}`);
}

export function getAnomalySummary() {
  return request<AnomalySummary>('/anomalies/summary');
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

// ── Setup / SDK health ────────────────────────────────────────────────────────

export interface SetupStatus {
  last_event_at:   string | null;
  last_event_name: string | null;
  total_events:    number;
}

export function getSetupStatus() {
  return request<SetupStatus>('/setup/status');
}

// ── AI Copilot ────────────────────────────────────────────────────────────────

export interface CopilotQueryResponse {
  question:   string;
  sql:        string;
  columns:    string[];
  rows:       (string | number | boolean | null)[][];
  chart_type: 'bar' | 'line' | 'pie' | 'number' | 'table';
  x_key:      string;
  y_key:      string;
  title:      string;
  insight:    string;
}

export function copilotQuery(question: string) {
  return request<CopilotQueryResponse>('/copilot/query', {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
}

export function copilotSuggestions() {
  return request<{ suggestions: string[] }>('/copilot/suggestions');
}

// ── Feature Flags ─────────────────────────────────────────────────────────────

export interface FeatureFlag {
  id:          string;
  name:        string;
  description: string;
  enabled:     boolean;
  rollout_pct: number;
  targeting:   { attribute: string; operator: string; value: unknown }[];
  created_at:  string;
  updated_at:  string;
}

export function listFlags() {
  return request<FeatureFlag[]>('/flags');
}

export function createFlag(payload: {
  name:        string;
  description?: string;
  enabled?:    boolean;
  rollout_pct?: number;
}) {
  return request<FeatureFlag>('/flags', {
    method: 'POST',
    body:   JSON.stringify(payload),
  });
}

export function updateFlag(id: string, patch: Partial<Pick<FeatureFlag, 'description' | 'enabled' | 'rollout_pct' | 'targeting'>>) {
  return request<FeatureFlag>(`/flags/${id}`, {
    method: 'PATCH',
    body:   JSON.stringify(patch),
  });
}

export function deleteFlag(id: string) {
  return request<void>(`/flags/${id}`, { method: 'DELETE' });
}

// ── Heatmaps ──────────────────────────────────────────────────────────────────

export interface HeatmapPage {
  page_url:  string;
  clicks:    number;
  scrolls:   number;
  last_seen: string | null;
}

export function listHeatmapPages() {
  return request<HeatmapPage[]>('/heatmap/pages');
}

export function getHeatmapClicks(pageUrl: string, days = 30) {
  const params = new URLSearchParams({ page_url: pageUrl, days: String(days) });
  return request<{ cells: { row: number; col: number; intensity: number; count: number }[]; total_clicks: number }>(
    `/heatmap/clicks?${params}`,
  );
}

export function getHeatmapScroll(pageUrl: string, days = 30) {
  const params = new URLSearchParams({ page_url: pageUrl, days: String(days) });
  return request<{ buckets: { depth: number; sessions: number; pct: number }[]; total_sessions: number }>(
    `/heatmap/scroll?${params}`,
  );
}

// ── People / User Profiles ────────────────────────────────────────────────────

export interface UserProfile {
  user_id:      string;
  total_events: number;
  track_events: number;
  first_seen:   string | null;
  last_seen:    string | null;
  traits:       Record<string, unknown>;
}

export interface UserEvent {
  name:        string;
  properties:  Record<string, unknown>;
  received_at: string;
}

export interface UserDetail {
  user_id:      string;
  traits:       Record<string, unknown>;
  total_events: number;
  events:       UserEvent[];
  limit:        number;
  offset:       number;
}

export function listPeople(q?: string, limit = 50, offset = 0) {
  const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (q) p.set('q', q);
  return request<{ users: UserProfile[]; total: number; limit: number; offset: number }>(
    `/people?${p}`,
  );
}

export function getPerson(userId: string, limit = 50, offset = 0) {
  const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return request<UserDetail>(`/people/${encodeURIComponent(userId)}?${p}`);
}

// ── Churn Prediction ──────────────────────────────────────────────────────────

export type RiskLevel = 'healthy' | 'warning' | 'at_risk' | 'critical';

export interface ChurnUser {
  user_id:       string;
  last_seen:     string | null;
  events_7d:     number;
  events_30d:    number;
  days_inactive: number;
  risk_level:    RiskLevel;
  risk_score:    number;
  traits:        Record<string, unknown>;
}

export interface ChurnSummary {
  healthy:  number;
  warning:  number;
  at_risk:  number;
  critical: number;
  total:    number;
}

export function getChurnSummary() {
  return request<ChurnSummary>('/churn/summary');
}

export function listChurn(risk?: RiskLevel, limit = 100) {
  const p = new URLSearchParams({ limit: String(limit) });
  if (risk) p.set('risk', risk);
  return request<ChurnUser[]>(`/churn?${p}`);
}

// ── Warehouse Sync ────────────────────────────────────────────────────────────

export interface WarehouseStats {
  events:       number;
  orders:       number;
  users:        number;
  oldest_event: string | null;
}

export function getWarehouseStats() {
  return request<WarehouseStats>('/warehouse/stats');
}

// ── GDPR ──────────────────────────────────────────────────────────────────────

export interface GdprOptOut {
  user_id:      string;
  opted_out_at: string;
}

export interface GdprExport {
  user_id:      string;
  queried_as:   string | null;   // set when email resolved to a user_id
  opted_out:    boolean;
  total_events: number;
  events: Array<{
    event_name:   string;
    properties:   Record<string, unknown>;
    received_at:  string;
    anonymous_id: string | null;
  }>;
}

export function listOptOuts() {
  return request<GdprOptOut[]>('/gdpr/opt-outs');
}

export function gdprExport(userId: string) {
  return request<GdprExport>(`/gdpr/export/${encodeURIComponent(userId)}`);
}

export function gdprOptOut(userId: string) {
  return request<{ user_id: string; opted_out: boolean }>('/gdpr/opt-out', {
    method: 'POST',
    body:   JSON.stringify({ user_id: userId }),
  });
}

export function gdprRemoveOptOut(userId: string) {
  return request<{ user_id: string; opted_out: boolean }>(
    `/gdpr/opt-out/${encodeURIComponent(userId)}`,
    { method: 'DELETE' },
  );
}

export function gdprForget(userId: string) {
  return request<{ user_id: string; events_deleted: number; forgotten: boolean }>(
    `/gdpr/forget/${encodeURIComponent(userId)}`,
    { method: 'DELETE' },
  );
}

// ── Audit Log ─────────────────────────────────────────────────────────────────

export interface AuditEntry {
  id:            string;
  actor_email:   string;
  action:        string;
  resource_type: string | null;
  resource_id:   string | null;
  metadata:      Record<string, unknown>;
  created_at:    string;
}

export interface AuditPage {
  entries: AuditEntry[];
  total:   number;
  limit:   number;
  offset:  number;
}

export function listAudit(params: { category?: string; limit?: number; offset?: number } = {}) {
  const p = new URLSearchParams();
  if (params.category) p.set('category', params.category);
  if (params.limit)    p.set('limit',    String(params.limit));
  if (params.offset)   p.set('offset',   String(params.offset));
  return request<AuditPage>(`/audit?${p}`);
}

// ── Storage ───────────────────────────────────────────────────────────────────

export interface StorageStats {
  hot_events:          number;
  archived_events:     number;
  total_events:        number;
  oldest_hot:          string | null;
  oldest_archived:     string | null;
  estimated_hot_mb:    number;
  estimated_archive_mb: number;
}

export interface ArchivedEvent {
  event_name:  string;
  user_id:     string | null;
  properties:  Record<string, unknown>;
  received_at: string;
  archived_at: string;
}

export function getStorageStats() {
  return request<StorageStats>('/storage/stats');
}

export function archiveEvents(olderThanDays: number) {
  return request<{ events_archived: number; older_than_days: number }>('/storage/archive', {
    method: 'POST',
    body:   JSON.stringify({ older_than_days: olderThanDays }),
  });
}

export function listArchivedEvents(params: {
  user_id?: string; event_name?: string; limit?: number; offset?: number;
} = {}) {
  const p = new URLSearchParams();
  if (params.user_id)    p.set('user_id',    params.user_id);
  if (params.event_name) p.set('event_name', params.event_name);
  if (params.limit)      p.set('limit',      String(params.limit));
  if (params.offset)     p.set('offset',     String(params.offset));
  return request<ArchivedEvent[]>(`/storage/archived?${p}`);
}

export async function downloadWarehouseExport(
  dataset: 'events' | 'orders' | 'users',
  opts: { since?: string; until?: string; fmt?: 'json' | 'csv'; limit?: number } = {},
): Promise<void> {
  const p = new URLSearchParams();
  if (opts.since)  p.set('since',  opts.since);
  if (opts.until)  p.set('until',  opts.until);
  if (opts.fmt)    p.set('fmt',    opts.fmt ?? 'json');
  if (opts.limit)  p.set('limit',  String(opts.limit ?? 50000));

  const res = await fetch(`${BASE}/warehouse/export/${dataset}?${p}`, {
    headers: { 'Content-Type': 'application/json', ...authHeader() },
  });
  if (!res.ok) throw new Error(`Export failed: HTTP ${res.status}`);

  const blob = await res.blob();
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `${dataset}.${opts.fmt ?? 'json'}`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Path Analysis ─────────────────────────────────────────────────────────────

export interface PathStep {
  step: number;
  event_name: string;
  users: number;
  pct_of_prev: number;
}

export interface PathRow {
  steps: string[];
  users: number;
}

export function getPathEvents() {
  return request<string[]>('/paths/events');
}

export function getPaths(params: { start_event: string; steps?: number }) {
  const p = new URLSearchParams({ start_event: params.start_event });
  if (params.steps) p.set('steps', String(params.steps));
  return request<{ paths: PathRow[]; summary: PathStep[] }>(`/paths?${p}`);
}

// ── Schema Registry ──────────────────────────────────────────────────────────

export interface EventSchema {
  id: number;
  event_name: string;
  schema: Record<string, { type: string; required?: boolean }>;
  strict_mode: boolean;
  created_at: string;
  updated_at: string;
}

export interface SchemaViolation {
  id: number;
  event_name: string;
  violation_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface PiiSummaryRow {
  event_name: string;
  fields_redacted: string[];
  sample_count: number;
  last_seen_at: string;
}

export function listSchemas() {
  return request<EventSchema[]>('/schema');
}

export function upsertSchema(payload: { event_name: string; schema: Record<string, unknown>; strict_mode?: boolean }) {
  return request<EventSchema>('/schema', { method: 'POST', body: JSON.stringify(payload) });
}

export function deleteSchema(eventName: string) {
  return request<{ deleted: boolean }>(`/schema/${encodeURIComponent(eventName)}`, { method: 'DELETE' });
}

export function listSchemaViolations() {
  return request<SchemaViolation[]>('/schema/violations');
}

export function getPiiSummary() {
  return request<PiiSummaryRow[]>('/schema/pii-summary');
}

export function inferSchema(eventName: string) {
  return request<{ event_name: string; inferred: Record<string, unknown> }>(`/schema/infer/${encodeURIComponent(eventName)}`);
}

// ── API Keys ──────────────────────────────────────────────────────────────────

export interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
}

export function listApiKeys() {
  return request<ApiKey[]>('/api-keys');
}

export function createApiKey(payload: { name: string; scopes: string[] }) {
  return request<ApiKey & { key: string }>('/api-keys', { method: 'POST', body: JSON.stringify(payload) });
}

export function revokeApiKey(id: number) {
  return request<{ revoked: boolean }>(`/api-keys/${id}`, { method: 'DELETE' });
}

// ── Scheduled Reports ─────────────────────────────────────────────────────────

export interface ScheduledReport {
  id: number;
  name: string;
  metric: string;
  period: string;
  recipients: string[];
  cron: string;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
}

export function listReports() {
  return request<ScheduledReport[]>('/reports');
}

export function createReport(payload: { name: string; metric: string; period: string; recipients: string[]; cron: string }) {
  return request<ScheduledReport>('/reports', { method: 'POST', body: JSON.stringify(payload) });
}

export function updateReport(id: number, patch: Partial<Pick<ScheduledReport, 'enabled'>>) {
  return request<ScheduledReport>(`/reports/${id}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export function deleteReport(id: number) {
  return request<{ deleted: boolean }>(`/reports/${id}`, { method: 'DELETE' });
}

export function runReport(id: number) {
  return request<{ result: unknown; sent_to: string[] }>(`/reports/${id}/run`, { method: 'POST' });
}

// ── System Health ─────────────────────────────────────────────────────────────

export interface SystemHealth {
  status: string;
  db_latency_ms: number;
  ingest_lag_s: number | null;
  events_24h: number;
  checked_at: string;
}

export interface SystemStats {
  total_all_time: number;
  last_hour: number;
  last_day: number;
  last_week: number;
  top_events_24h: { event_name: string; count: number }[];
}

export function getSystemHealth() {
  return request<SystemHealth>('/system/health');
}

export function getSystemStats() {
  return request<SystemStats>('/system/stats');
}

// ── Embed Tokens ──────────────────────────────────────────────────────────────

export interface EmbedToken {
  id: number;
  name: string;
  widget_type: string;
  config: Record<string, unknown>;
  expires_at: string | null;
  created_at: string;
  token_prefix: string;
}

export function listEmbedTokens() {
  return request<EmbedToken[]>('/embed/tokens');
}

export function createEmbedToken(payload: { name: string; widget_type: string; config?: Record<string, unknown>; expires_days?: number }) {
  return request<EmbedToken & { token: string }>('/embed/tokens', { method: 'POST', body: JSON.stringify(payload) });
}

export function revokeEmbedToken(id: number) {
  return request<{ revoked: boolean }>(`/embed/tokens/${id}`, { method: 'DELETE' });
}


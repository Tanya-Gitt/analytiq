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
export interface SegmentBDashboard {
  revenue_trend: RevenueTrendPoint[];
  top_channels: TopChannel[];
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
export interface SegmentADashboard {
  events_timeline: EventsTimelinePoint[];
  top_events: TopEvent[];
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

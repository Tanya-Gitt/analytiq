/**
 * Analytics Platform — Node.js / TypeScript Server SDK
 *
 * Zero dependencies — uses Node.js built-in `https` / `http` modules.
 * Works in Node 18+ (native fetch available) and older Node via https module.
 *
 * Usage (ESM / TypeScript):
 *   import { Analytics } from '@analytiq/node';
 *   const client = new Analytics('YOUR_API_KEY', { host: 'https://your-host.com' });
 *   await client.track('purchase', { userId: 'u_123', properties: { sku: 'P1', price: 29 } });
 *   await client.identify('u_123', { email: 'alice@example.com' });
 *   await client.page({ userId: 'u_123', properties: { url: '/checkout' } });
 *
 * Usage (CommonJS):
 *   const { Analytics } = require('@analytiq/node');
 */

export interface AnalyticsOptions {
  /** Base URL of the analytics server. Default: https://your-analytics-host.com */
  host?: string;
  /** Request timeout in milliseconds. Default: 10 000 */
  timeout?: number;
}

export interface TrackOptions {
  userId?: string;
  anonymousId?: string;
  properties?: Record<string, unknown>;
}

export interface PageOptions {
  userId?: string;
  anonymousId?: string;
  properties?: Record<string, unknown>;
}

export class AnalyticsError extends Error {
  constructor(public readonly status: number, message: string) {
    super(`HTTP ${status}: ${message}`);
    this.name = 'AnalyticsError';
  }
}

// ── Core payload shape sent to the server ─────────────────────────────────────

interface IngestPayload {
  type: 'track' | 'identify' | 'page';
  event?: string;
  userId?: string;
  anonymousId?: string;
  properties?: Record<string, unknown>;
}

// ── Client ────────────────────────────────────────────────────────────────────

export class Analytics {
  private readonly url: string;
  private readonly timeout: number;

  constructor(apiKey: string, options: AnalyticsOptions = {}) {
    const host = (options.host ?? 'https://your-analytics-host.com').replace(/\/$/, '');
    this.url     = `${host}/api/ingest/${apiKey}`;
    this.timeout = options.timeout ?? 10_000;
  }

  /** Record a named action performed by a user. */
  async track(event: string, opts: TrackOptions = {}): Promise<void> {
    await this._send({
      type:        'track',
      event,
      userId:      opts.userId,
      anonymousId: opts.anonymousId,
      properties:  opts.properties,
    });
  }

  /** Associate traits (email, plan, etc.) with a user. */
  async identify(userId: string, traits: Record<string, unknown> = {}): Promise<void> {
    await this._send({ type: 'identify', userId, properties: traits });
  }

  /** Record a page view. */
  async page(opts: PageOptions = {}): Promise<void> {
    await this._send({
      type:        'page',
      userId:      opts.userId,
      anonymousId: opts.anonymousId,
      properties:  opts.properties,
    });
  }

  // ── internals ──────────────────────────────────────────────────────────────

  private async _send(payload: IngestPayload): Promise<void> {
    // Strip undefined keys
    const body = JSON.stringify(
      Object.fromEntries(Object.entries(payload).filter(([, v]) => v !== undefined))
    );

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    let res: Response;
    try {
      res = await fetch(this.url, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const json = await res.json() as { detail?: string };
        if (json.detail) detail = json.detail;
      } catch { /* ignore parse errors */ }
      throw new AnalyticsError(res.status, detail);
    }
  }
}

export default Analytics;

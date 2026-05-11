'use client';

import { useEffect, useRef, useState } from 'react';
import AppShell from '@/components/layout/AppShell';
import { authHeader } from '@/lib/auth';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface LiveEvent {
  id: number;
  event_name: string;
  user_id: string | null;
  received_at: string;
  properties: Record<string, unknown>;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 5_000)  return 'just now';
  if (diff < 60_000) return `${Math.floor(diff / 1_000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  return new Date(iso).toLocaleTimeString();
}

const EVENT_COLORS: Record<string, string> = {
  page_view:          'bg-blue-100 text-blue-700',
  product_viewed:     'bg-indigo-100 text-indigo-700',
  add_to_cart:        'bg-amber-100 text-amber-700',
  checkout_started:   'bg-orange-100 text-orange-700',
  purchase_completed: 'bg-green-100 text-green-700',
};

function eventColor(name: string) {
  return EVENT_COLORS[name] ?? 'bg-gray-100 text-gray-700';
}

// ── EventRow ──────────────────────────────────────────────────────────────────

function EventRow({ event, isNew }: { event: LiveEvent; isNew: boolean }) {
  const [highlight, setHighlight] = useState(isNew);

  useEffect(() => {
    if (!isNew) return;
    const t = setTimeout(() => setHighlight(false), 1_500);
    return () => clearTimeout(t);
  }, [isNew]);

  const propKeys = Object.keys(event.properties ?? {});

  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 border-b border-gray-100 transition-colors duration-700 ${
        highlight ? 'bg-indigo-50' : 'bg-white'
      }`}
    >
      {/* Event name badge */}
      <span
        className={`shrink-0 mt-0.5 text-xs font-semibold px-2 py-0.5 rounded-full ${eventColor(event.event_name)}`}
      >
        {event.event_name}
      </span>

      {/* Detail */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {event.user_id && (
            <span className="font-mono truncate max-w-[140px]" title={event.user_id}>
              {event.user_id}
            </span>
          )}
          {propKeys.length > 0 && (
            <span className="text-gray-400 truncate">
              {propKeys.slice(0, 3).map(k => `${k}: ${String(event.properties[k])}`).join(', ')}
            </span>
          )}
        </div>
      </div>

      {/* Timestamp */}
      <span className="shrink-0 text-xs text-gray-400 whitespace-nowrap">
        {relativeTime(event.received_at)}
      </span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const MAX_EVENTS = 200;

export default function LivePage() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [newIds, setNewIds] = useState<Set<number>>(() => new Set<number>());
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState('');
  const [paused, setPaused] = useState(false);
  const [total, setTotal] = useState(0);

  const abortRef = useRef<AbortController | null>(null);
  const pausedRef = useRef(false);

  pausedRef.current = paused;

  function startStream(cursorOverride?: number) {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setError('');

    const headers = authHeader();
    const url = cursorOverride != null
      ? `${BASE}/stream/events?cursor=${cursorOverride}`
      : `${BASE}/stream/events`;

    (async () => {
      try {
        const res = await fetch(url, {
          headers,
          signal: ctrl.signal,
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          setError(body?.detail ?? `HTTP ${res.status}`);
          setConnected(false);
          return;
        }

        setConnected(true);
        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });

          // Parse SSE frames — split on double-newline
          const frames = buf.split('\n\n');
          buf = frames.pop() ?? '';   // keep incomplete tail

          for (const frame of frames) {
            if (!frame.trim() || frame.startsWith(':')) continue;  // comment / keepalive
            const lines = frame.split('\n');
            let data = '';
            for (const line of lines) {
              if (line.startsWith('data: ')) data = line.slice(6);
            }
            if (!data) continue;

            try {
              const evt: LiveEvent = JSON.parse(data);
              if (!pausedRef.current) {
                setTotal(n => n + 1);
                setNewIds(prev => { const s = new Set(Array.from(prev)); s.add(evt.id); return s; });
                setEvents(prev => [evt, ...prev].slice(0, MAX_EVENTS));
              }
            } catch {
              // malformed frame — ignore
            }
          }
        }
      } catch (err: unknown) {
        if ((err as Error)?.name === 'AbortError') return;
        setConnected(false);
        setError((err as Error).message ?? 'Stream disconnected');
        // Auto-reconnect after 5 s
        setTimeout(() => startStream(), 5_000);
      }
    })();
  }

  useEffect(() => {
    startStream();
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleClear() {
    setEvents([]);
    setTotal(0);
    setNewIds(new Set<number>());
  }

  return (
    <AppShell>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            Live Feed
            {connected && (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                Live
              </span>
            )}
            {!connected && !error && (
              <span className="text-xs font-medium text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                Connecting…
              </span>
            )}
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Real-time product events as they arrive — {total.toLocaleString()} received this session
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setPaused(p => !p)}
            className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
              paused
                ? 'border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100'
                : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            {paused ? '▶ Resume' : '⏸ Pause'}
          </button>
          <button
            onClick={handleClear}
            className="text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Connection error: {error}
          <button
            onClick={() => startStream()}
            className="ml-3 underline text-red-600 hover:text-red-800"
          >
            Retry
          </button>
        </div>
      )}

      {/* Pause notice */}
      {paused && (
        <div className="mb-4 rounded-lg bg-amber-50 border border-amber-200 px-4 py-2 text-sm text-amber-700">
          Stream paused — new events are not displayed until you resume.
        </div>
      )}

      {/* Event list */}
      <div className="card p-0 overflow-hidden">
        {/* Legend */}
        <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-100 flex items-center gap-4 flex-wrap">
          {Object.entries(EVENT_COLORS).map(([name, cls]) => (
            <span key={name} className={`text-xs font-medium px-2 py-0.5 rounded-full ${cls}`}>
              {name}
            </span>
          ))}
          <span className="text-xs text-gray-400 ml-auto">
            Last {MAX_EVENTS} events
          </span>
        </div>

        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400 text-sm">
            <svg className="w-10 h-10 mb-3 text-gray-300" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
            </svg>
            {connected
              ? 'Waiting for events… send one via the JS SDK or POST /api/ingest/events'
              : 'Connecting to stream…'}
          </div>
        ) : (
          <div className="divide-y divide-gray-50 max-h-[calc(100vh-220px)] overflow-y-auto">
            {events.map(evt => (
              <EventRow
                key={evt.id}
                event={evt}
                isNew={newIds.has(evt.id)}
              />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

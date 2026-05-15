'use client';

import { useState, useEffect, useRef } from 'react';
import AppShell from '@/components/layout/AppShell';

interface LiveEvent {
  id: string;
  event_name: string;
  user_id: string | null;
  anonymous_id: string | null;
  properties: Record<string, unknown>;
  received_at: string;
  pii_fields?: string[];
}

// ── Synthetic event stream ────────────────────────────────────────────────────
//
// The real-time SSE stream requires a long-lived connection to the FastAPI
// backend, which sleeps on Render's free tier. To keep this view useful for
// demo visitors we simulate a realistic event firehose locally — same shape
// as the real `/stream/live` payload.

const USERS = [
  'usr_regular_065', 'usr_power_035',     'usr_regular_113',
  'usr_occasional_016', 'usr_regular_079', 'usr_regular_155',
  'usr_regular_130', 'usr_regular_027', null, null,
];

const PAGES    = ['/dashboard', '/funnels', '/people', '/copilot', '/heatmaps', '/pricing', '/settings'];
const FEATURES = ['cohort_export', 'funnel_builder', 'sql_runner', 'pdf_report', 'flag_create'];
const PLANS    = ['free', 'starter', 'pro', 'enterprise'];

type EventTemplate = () => Pick<LiveEvent, 'event_name' | 'properties' | 'pii_fields'>;

const TEMPLATES: EventTemplate[] = [
  () => ({
    event_name: 'page_view',
    properties: {
      page:       PAGES[Math.floor(Math.random() * PAGES.length)],
      duration_s: Math.floor(Math.random() * 240),
      referrer:   'https://twitter.com',
    },
  }),
  () => ({
    event_name: 'feature_used',
    properties: { feature: FEATURES[Math.floor(Math.random() * FEATURES.length)] },
  }),
  () => ({
    event_name: 'button_click',
    properties: { label: 'Upgrade plan', location: 'navbar' },
  }),
  () => ({
    event_name: 'purchase',
    properties: {
      plan:    PLANS[Math.floor(Math.random() * PLANS.length)],
      amount:  [49, 99, 199, 588, 1188][Math.floor(Math.random() * 5)],
      billing: Math.random() < 0.4 ? 'annual' : 'monthly',
    },
  }),
  () => ({
    event_name: 'identify',
    properties: {
      email: '[REDACTED]',
      name:  '[REDACTED]',
      plan:  PLANS[Math.floor(Math.random() * PLANS.length)],
    },
    pii_fields: ['email', 'name'],
  }),
  () => ({
    event_name: 'signup',
    properties: {
      email:  '[REDACTED]',
      source: 'organic',
    },
    pii_fields: ['email'],
  }),
  () => ({
    event_name: 'session_start',
    properties: {
      utm_source:   ['twitter', 'google', 'linkedin', 'direct'][Math.floor(Math.random() * 4)],
      utm_campaign: 'q2_launch',
      device:       Math.random() < 0.6 ? 'desktop' : 'mobile',
    },
  }),
];

function makeFakeEvent(): LiveEvent {
  const tpl  = TEMPLATES[Math.floor(Math.random() * TEMPLATES.length)]();
  const user = USERS[Math.floor(Math.random() * USERS.length)];
  return {
    id:           `${Date.now()}-${Math.random()}`,
    event_name:   tpl.event_name,
    user_id:      user,
    anonymous_id: user ? null : `anon_${Math.random().toString(36).slice(2, 10)}`,
    properties:   tpl.properties,
    received_at:  new Date().toISOString(),
    pii_fields:   tpl.pii_fields,
  };
}

export default function LiveDebuggerPage() {
  const [events, setEvents]     = useState<LiveEvent[]>([]);
  const [paused, setPaused]     = useState(false);
  const [filter, setFilter]     = useState('');
  const [selected, setSelected] = useState<LiveEvent | null>(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    // Seed with a small backlog so the view isn't empty on first paint.
    setEvents(Array.from({ length: 6 }, () => {
      const ev = makeFakeEvent();
      ev.received_at = new Date(Date.now() - Math.random() * 60_000).toISOString();
      return ev;
    }));

    const tick = () => {
      if (!pausedRef.current) {
        setEvents(prev => [makeFakeEvent(), ...prev].slice(0, 200));
      }
    };
    // Random cadence between 800ms and 2200ms feels like a real firehose.
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timer = setTimeout(() => { tick(); schedule(); }, 800 + Math.random() * 1400);
    };
    schedule();
    return () => clearTimeout(timer);
  }, []);

  const filtered = filter
    ? events.filter(e =>
        e.event_name.toLowerCase().includes(filter.toLowerCase()) ||
        (e.user_id || '').toLowerCase().includes(filter.toLowerCase())
      )
    : events;

  function clearEvents() {
    setEvents([]);
    setSelected(null);
  }

  return (
    <AppShell>
      <div className="p-6 max-w-6xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Live Events Debugger</h1>
            <p className="text-sm text-gray-500 mt-1">Real-time event stream with PII detection</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full bg-green-100 text-green-700">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              Live (demo)
            </span>
            <button
              className={`text-xs px-3 py-1.5 border rounded-lg font-medium transition-colors ${paused ? 'bg-green-600 text-white border-green-600' : 'bg-yellow-100 text-yellow-800 border-yellow-300 hover:bg-yellow-200'}`}
              onClick={() => setPaused(v => !v)}
            >
              {paused ? '▶ Resume' : '⏸ Pause'}
            </button>
            <button className="text-xs px-3 py-1.5 border rounded-lg hover:bg-gray-50 text-gray-600" onClick={clearEvents}>
              Clear
            </button>
          </div>
        </div>

        {/* Demo-data disclaimer */}
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5 flex gap-2.5">
          <span className="text-amber-600 text-sm shrink-0 mt-0.5">ℹ️</span>
          <div className="text-[11px] text-amber-900 leading-relaxed">
            <p className="font-semibold mb-0.5">Simulated event stream · sample data</p>
            <p className="text-amber-800">
              The real <code className="px-1 bg-amber-100 rounded">/stream/live</code> SSE
              endpoint requires a long-lived connection to the backend, which sleeps on
              free-tier Render. To keep this view usable for demo visitors, events are
              generated in-browser with the same payload shape as production. Pause,
              filter, click-to-inspect and PII detection all work the same way.
            </p>
          </div>
        </div>

        {/* Filter */}
        <input
          className="input w-full"
          placeholder="Filter by event name or user ID…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />

        <div className="flex gap-4">
          {/* Event list */}
          <div className="flex-1 border border-gray-200 rounded-lg overflow-y-auto max-h-[calc(100vh-320px)] divide-y divide-gray-100">
            {filtered.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-gray-400">
                Waiting for events…
              </div>
            ) : (
              filtered.map(ev => (
                <div
                  key={ev.id}
                  className={`px-4 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors ${selected?.id === ev.id ? 'bg-blue-50' : ''}`}
                  onClick={() => setSelected(ev)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium text-gray-800">{ev.event_name}</span>
                      {ev.pii_fields && ev.pii_fields.length > 0 && (
                        <span className="text-xs px-1.5 py-0.5 bg-orange-100 text-orange-700 rounded font-medium">
                          PII: {ev.pii_fields.join(', ')}
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-gray-400">{new Date(ev.received_at).toLocaleTimeString()}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {ev.user_id || ev.anonymous_id || 'anonymous'}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Detail panel */}
          {selected && (
            <div className="w-80 border border-gray-200 rounded-lg p-4 space-y-3 max-h-[calc(100vh-320px)] overflow-y-auto">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-gray-800 font-mono text-sm">{selected.event_name}</h3>
                <button className="text-xs text-gray-400 hover:text-gray-600" onClick={() => setSelected(null)}>✕</button>
              </div>

              <div className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500">user_id</span>
                  <span className="font-mono text-gray-700">{selected.user_id || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">anon_id</span>
                  <span className="font-mono text-gray-700 truncate max-w-36">{selected.anonymous_id || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">received</span>
                  <span className="text-gray-700">{new Date(selected.received_at).toLocaleTimeString()}</span>
                </div>
              </div>

              {selected.pii_fields && selected.pii_fields.length > 0 && (
                <div className="bg-orange-50 border border-orange-200 rounded p-2 text-xs text-orange-700">
                  ⚠ PII detected & redacted: {selected.pii_fields.join(', ')}
                </div>
              )}

              <div>
                <p className="text-xs font-medium text-gray-600 mb-1">Properties</p>
                <pre className="bg-gray-50 rounded p-2 text-xs text-gray-700 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(selected.properties, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Stats bar */}
        <div className="flex items-center gap-6 text-xs text-gray-500">
          <span>{events.length} events buffered (max 200)</span>
          {paused && <span className="text-yellow-600 font-medium">⏸ Paused — new events not shown</span>}
        </div>
      </div>
    </AppShell>
  );
}

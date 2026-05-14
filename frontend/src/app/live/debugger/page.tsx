'use client';

import { useState, useEffect, useRef } from 'react';
import AppShell from '@/components/layout/AppShell';
import { getToken } from '@/lib/auth';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';

interface LiveEvent {
  id: string;
  event_name: string;
  user_id: string | null;
  anonymous_id: string | null;
  properties: Record<string, unknown>;
  received_at: string;
  pii_fields?: string[];
}

export default function LiveDebuggerPage() {
  const [events, setEvents]       = useState<LiveEvent[]>([]);
  const [paused, setPaused]       = useState(false);
  const [filter, setFilter]       = useState('');
  const [selected, setSelected]   = useState<LiveEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const pausedRef  = useRef(paused);
  const eventsRef  = useRef(events);
  const esRef      = useRef<EventSource | null>(null);

  pausedRef.current = paused;
  eventsRef.current = events;

  useEffect(() => {
    const token = getToken();
    const es = new EventSource(`${BASE}/stream/live?token=${token}`);
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.onmessage = (e) => {
      if (pausedRef.current) return;
      try {
        const ev: LiveEvent = JSON.parse(e.data);
        ev.id = `${Date.now()}-${Math.random()}`;
        setEvents(prev => [ev, ...prev].slice(0, 200));
      } catch {
        // ignore parse errors
      }
    };

    return () => es.close();
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
            <span className={`flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full ${connected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
              <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
              {connected ? 'Live' : 'Disconnected'}
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

        {/* Filter */}
        <input
          className="input w-full"
          placeholder="Filter by event name or user ID…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />

        <div className="flex gap-4">
          {/* Event list */}
          <div className="flex-1 border border-gray-200 rounded-lg overflow-y-auto max-h-[calc(100vh-280px)] divide-y divide-gray-100">
            {filtered.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-gray-400">
                {connected ? 'Waiting for events…' : 'Connecting to event stream…'}
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
            <div className="w-80 border border-gray-200 rounded-lg p-4 space-y-3 max-h-[calc(100vh-280px)] overflow-y-auto">
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

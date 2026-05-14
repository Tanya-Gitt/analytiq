'use client';

import { useState, useEffect } from 'react';
import AppShell from '@/components/layout/AppShell';
import { authHeader } from '@/lib/auth';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';

interface PathResult {
  steps:       string[];
  users:       number;
}

interface PathsResponse {
  paths:       PathResult[];
  start_event: string;
  total_users: number;
  steps:       number;
}

function pct(users: number, total: number) {
  if (!total) return 0;
  return Math.round((users / total) * 100);
}

function retentionColor(p: number) {
  if (p >= 60) return 'bg-green-500';
  if (p >= 30) return 'bg-yellow-400';
  return 'bg-red-400';
}

function retentionText(p: number) {
  if (p >= 60) return 'text-green-700';
  if (p >= 30) return 'text-yellow-700';
  return 'text-red-600';
}

export default function PathsPage() {
  const [events,      setEvents]      = useState<string[]>([]);
  const [startEvent,  setStartEvent]  = useState('');
  const [steps,       setSteps]       = useState(3);
  const [data,        setData]        = useState<PathsResponse | null>(null);
  const [loading,     setLoading]     = useState(false);

  useEffect(() => {
    fetch(`${BASE}/paths/events`, { headers: authHeader() })
      .then(r => r.json())
      .then((list: string[]) => {
        setEvents(list);
        if (list.length) setStartEvent(list[0]);
      })
      .catch(() => {});
  }, []);

  async function analyze() {
    if (!startEvent) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${BASE}/paths?start_event=${encodeURIComponent(startEvent)}&steps=${steps}&limit=8`,
        { headers: authHeader() },
      );
      setData(await res.json());
    } finally {
      setLoading(false);
    }
  }

  // Build columns: for each step index, collect unique events + their user counts.
  // Use the step-1 chain total as the denominator so step 1 always shows 100%
  // (a user with multiple start events creates >1 chain, so chain total ≥ unique users).
  const columns: Array<{ event: string; users: number }[]> = [];
  let chainTotal = data?.total_users ?? 1;
  if (data) {
    for (let col = 0; col < data.steps; col++) {
      const map = new Map<string, number>();
      for (const path of data.paths) {
        const ev = path.steps[col];
        map.set(ev, (map.get(ev) ?? 0) + path.users);
      }
      const sorted = Array.from(map.entries())
        .map(([event, users]) => ({ event, users }))
        .sort((a, b) => b.users - a.users);
      // Capture step-1 total so all columns use the same base
      if (col === 0) chainTotal = sorted.reduce((s, i) => s + i.users, 0) || data.total_users;
      columns.push(sorted);
    }
  }

  return (
    <AppShell>
      <div className="p-6 max-w-6xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Path Analysis</h1>
          <p className="text-sm text-gray-500 mt-1">
            Discover the event sequences users actually take — not just the ones you pre-defined
          </p>
        </div>

        {/* Controls */}
        <div className="card flex flex-wrap gap-4 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium text-gray-600 mb-1">Starting event</label>
            <select className="input w-full" value={startEvent} onChange={e => setStartEvent(e.target.value)}>
              {events.map(ev => <option key={ev} value={ev}>{ev}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Steps</label>
            <select className="input" value={steps} onChange={e => setSteps(Number(e.target.value))}>
              {[2, 3, 4, 5].map(s => <option key={s} value={s}>{s} steps</option>)}
            </select>
          </div>
          <button className="btn-primary" onClick={analyze} disabled={loading || !startEvent}>
            {loading ? 'Analyzing…' : 'Analyze Paths'}
          </button>
        </div>

        {/* Waterfall viz */}
        {data && (
          <div className="space-y-6">
            <p className="text-sm text-gray-500">
              <strong className="text-gray-800">{data.total_users.toLocaleString()}</strong> unique users started with <strong className="font-mono">{data.start_event}</strong> in the last 30 days
            </p>

            {data.paths.length > 0 && <div className="overflow-x-auto">
              <div className="flex gap-2 min-w-max">
                {columns.map((col, ci) => (
                  <div key={ci} className="flex flex-col gap-2" style={{ width: 180 }}>
                    <div className="text-xs font-medium text-gray-400 uppercase tracking-wide text-center">
                      Step {ci + 1}
                    </div>
                    {col.slice(0, 5).map(item => {
                      const p = pct(item.users, chainTotal);
                      return (
                        <div key={item.event} className="border border-gray-200 rounded-lg p-3 bg-white shadow-sm">
                          <div className="text-xs font-medium text-gray-700 truncate mb-1" title={item.event}>
                            {item.event}
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${retentionColor(p)}`}
                                style={{ width: `${Math.min(p, 100)}%` }}
                              />
                            </div>
                            <span className={`text-xs font-bold ${retentionText(p)}`}>{p}%</span>
                          </div>
                          <div className="text-xs text-gray-400 mt-0.5">{item.users.toLocaleString()} users</div>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>}

            {/* Empty state when users exist but no paths at this step count */}
            {data.paths.length === 0 && data.total_users > 0 && (
              <div className="card py-10 text-center space-y-2">
                <p className="text-gray-700 font-medium">
                  No {data.steps}-step paths found for <span className="font-mono">{data.start_event}</span>
                </p>
                <p className="text-sm text-gray-500">
                  {data.steps <= 2
                    ? <>These {data.total_users} user{data.total_users !== 1 ? 's' : ''} don&apos;t have enough consecutive events recorded.</>
                    : <>These {data.total_users} user{data.total_users !== 1 ? 's' : ''} don&apos;t have {data.steps} consecutive events recorded. Try a lower step count.</>
                  }
                </p>
                {data.steps > 2 && (
                  <div className="flex justify-center gap-2 pt-2">
                    {[2, 3, 4].filter(s => s < data.steps).map(s => (
                      <button
                        key={s}
                        className="btn-secondary text-xs px-3 py-1"
                        onClick={() => setSteps(s)}
                      >
                        Try {s} steps
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Data table */}
            {data.paths.length > 0 && (
            <div className="card p-0 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Path</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Users</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">% of starters</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {data.paths.map((path, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">
                        {path.steps.join(' → ')}
                      </td>
                      <td className="px-4 py-3 text-right font-medium">{path.users.toLocaleString()}</td>
                      <td className={`px-4 py-3 text-right font-medium ${retentionText(pct(path.users, chainTotal))}`}>
                        {pct(path.users, chainTotal)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}
          </div>
        )}

        {!data && !loading && (
          <div className="card text-center py-12">
            <p className="text-gray-400 text-sm">Select a starting event and click Analyze Paths</p>
          </div>
        )}
      </div>
    </AppShell>
  );
}

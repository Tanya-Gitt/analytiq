'use client';

import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { getToken } from '@/lib/auth';

interface HealthData {
  status: string;
  db_latency_ms: number;
  ingest_lag_s: number | null;
  events_24h: number;
  checked_at: string;
}

interface StatsData {
  total_all_time: number;
  last_hour: number;
  last_day: number;
  last_week: number;
  top_events_24h: { event_name: string; count: number }[];
}

interface ThroughputPoint {
  time: string;
  events: number;
}

const fetcher = (url: string) =>
  fetch(`/api/${url}`, { headers: { Authorization: `Bearer ${getToken()}` } })
    .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); });

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'ok'       ? 'bg-green-100 text-green-700 border-green-200' :
    status === 'degraded' ? 'bg-yellow-100 text-yellow-700 border-yellow-200' :
                            'bg-red-100 text-red-700 border-red-200';
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${cls}`}>
      <span className={`w-2 h-2 rounded-full ${status === 'ok' ? 'bg-green-500' : status === 'degraded' ? 'bg-yellow-500' : 'bg-red-500'}`} />
      {status.toUpperCase()}
    </span>
  );
}

export default function SystemPage() {
  const { data: health } = useSWR<HealthData>('system/health', fetcher, { refreshInterval: 10000 });
  const { data: stats }  = useSWR<StatsData>('system/stats', fetcher, { refreshInterval: 30000 });
  const { data: throughput } = useSWR<ThroughputPoint[]>('system/throughput', fetcher, { refreshInterval: 30000 });

  const tpArr = Array.isArray(throughput) ? throughput : [];
  const maxTp = tpArr.length > 0 ? Math.max(...tpArr.map(t => t.events), 1) : 1;

  return (
    <AppShell>
      <div className="p-6 max-w-5xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Health</h1>
          <p className="text-sm text-gray-500 mt-1">Real-time platform monitoring</p>
        </div>

        {/* Health banner */}
        <div className="card flex items-center justify-between">
          <div className="flex items-center gap-4">
            <StatusBadge status={health?.status ?? 'ok'} />
            <span className="text-sm text-gray-600">
              Last checked: {health ? new Date(health.checked_at).toLocaleTimeString() : '—'}
            </span>
          </div>
          <div className="flex gap-8 text-center">
            <div>
              <p className="text-2xl font-bold text-blue-600">{health?.db_latency_ms ?? '—'}<span className="text-sm font-normal text-gray-500 ml-1">ms</span></p>
              <p className="text-xs text-gray-500 mt-0.5">DB Latency</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-purple-600">{health?.ingest_lag_s != null ? `${health.ingest_lag_s}s` : '—'}</p>
              <p className="text-xs text-gray-500 mt-0.5">Ingest Lag</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-800">{health?.events_24h?.toLocaleString() ?? '—'}</p>
              <p className="text-xs text-gray-500 mt-0.5">Events 24h</p>
            </div>
          </div>
        </div>

        {/* Volume stats */}
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'All Time',   value: stats?.total_all_time, color: 'text-gray-800' },
            { label: 'Last Week',  value: stats?.last_week,      color: 'text-blue-600' },
            { label: 'Last Day',   value: stats?.last_day,       color: 'text-indigo-600' },
            { label: 'Last Hour',  value: stats?.last_hour,      color: 'text-purple-600' },
          ].map(c => (
            <div key={c.label} className="card text-center">
              <p className={`text-2xl font-bold ${c.color}`}>
                {c.value != null ? c.value.toLocaleString() : '—'}
              </p>
              <p className="text-xs text-gray-500 mt-1">{c.label}</p>
            </div>
          ))}
        </div>

        {/* Throughput chart */}
        {tpArr.length > 0 && (
          <div className="card space-y-3">
            <h2 className="font-semibold text-gray-800">Events / 5 min (last 2 hours)</h2>
            <div className="flex items-end gap-1 h-24">
              {tpArr.map((pt, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-0.5" title={`${new Date(pt.time).toLocaleTimeString()}: ${pt.events}`}>
                  <div
                    className="w-full bg-blue-400 rounded-t"
                    style={{ height: `${Math.max(4, Math.round((pt.events / maxTp) * 88))}px` }}
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-between text-xs text-gray-400">
              <span>{tpArr[0] ? new Date(tpArr[0].time).toLocaleTimeString() : ''}</span>
              <span>{tpArr[tpArr.length - 1] ? new Date(tpArr[tpArr.length - 1].time).toLocaleTimeString() : ''}</span>
            </div>
          </div>
        )}

        {/* Top events */}
        {stats?.top_events_24h && stats.top_events_24h.length > 0 && (
          <div className="card space-y-3">
            <h2 className="font-semibold text-gray-800">Top Events (24h)</h2>
            <div className="space-y-2">
              {stats.top_events_24h.map((ev, i) => {
                const max = stats.top_events_24h[0].count;
                const pct = Math.round((ev.count / max) * 100);
                return (
                  <div key={i} className="flex items-center gap-3 text-sm">
                    <span className="font-mono font-medium w-44 truncate text-gray-700">{ev.event_name}</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-2">
                      <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-gray-500 text-xs w-12 text-right">{ev.count.toLocaleString()}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

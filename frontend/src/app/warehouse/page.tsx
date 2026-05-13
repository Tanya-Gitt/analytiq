'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { getWarehouseStats, downloadWarehouseExport } from '@/lib/api';

function fmtNum(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}

// ── Export card ───────────────────────────────────────────────────────────────

function ExportCard({
  dataset,
  label,
  description,
  icon,
  rowCount,
  oldestEvent,
}: {
  dataset:     'events' | 'orders' | 'users';
  label:       string;
  description: string;
  icon:        React.ReactNode;
  rowCount:    number;
  oldestEvent: string | null;
}) {
  const [fmt,       setFmt]       = useState<'json' | 'csv'>('json');
  const [since,     setSince]     = useState('');
  const [until,     setUntil]     = useState('');
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState('');

  async function doExport() {
    setLoading(true);
    setError('');
    try {
      await downloadWarehouseExport(dataset, { since: since || undefined, until: until || undefined, fmt });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Export failed');
    } finally {
      setLoading(false);
    }
  }

  const curlBase = `/api/warehouse/export/${dataset}`;
  const curlParts = [`-H "Authorization: Bearer $TOKEN"`];
  if (since) curlParts.push(`-G -d "since=${since}"`);
  if (until) curlParts.push(`-G -d "until=${until}"`);
  curlParts.push(`-G -d "fmt=${fmt}"`);
  const curlCmd = `curl ${curlParts.join(' ')} "${curlBase}"`;

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
            {icon}
          </div>
          <div>
            <p className="font-semibold text-gray-900">{label}</p>
            <p className="text-xs text-gray-500">{description}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-gray-900 tabular-nums">{fmtNum(rowCount)}</p>
          <p className="text-[10px] text-gray-400">rows available</p>
        </div>
      </div>

      {/* Filters */}
      {dataset !== 'users' && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-1">
              Since
            </label>
            <input
              type="date"
              value={since}
              onChange={e => setSince(e.target.value)}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-1.5
                         focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-gray-50"
            />
          </div>
          <div>
            <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-1">
              Until
            </label>
            <input
              type="date"
              value={until}
              onChange={e => setUntil(e.target.value)}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-1.5
                         focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-gray-50"
            />
          </div>
        </div>
      )}

      {/* Format + Download */}
      <div className="flex items-center gap-3 mb-4">
        <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
          {(['json', 'csv'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFmt(f)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors uppercase ${
                fmt === f ? 'bg-white text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <button
          onClick={doExport}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-1.5 bg-indigo-600 text-white
                     rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50
                     disabled:cursor-not-allowed transition-colors"
        >
          {loading ? (
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
          )}
          Download {fmt.toUpperCase()}
        </button>
        {error && <span className="text-xs text-red-500">{error}</span>}
      </div>

      {/* cURL */}
      <div className="bg-gray-900 rounded-xl px-4 py-3">
        <p className="text-[10px] text-gray-500 mb-1">cURL</p>
        <pre className="text-[10px] text-gray-300 font-mono overflow-x-auto whitespace-pre-wrap break-all">
          {curlCmd}
        </pre>
      </div>

      {oldestEvent && dataset === 'events' && (
        <p className="text-[10px] text-gray-400 mt-2">
          Oldest event: {new Date(oldestEvent).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function WarehousePage() {
  const { data: stats, isLoading } = useSWR('warehouse-stats', getWarehouseStats, {
    refreshInterval: 120_000,
  });

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto flex flex-col gap-6">

        {/* Header */}
        <div>
          <h1 className="text-xl font-bold text-gray-900">Warehouse Sync</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Export raw data as JSON or CSV · filter by date range · pipe to BigQuery, Snowflake, or S3
          </p>
        </div>

        {/* Stat banner */}
        {stats && (
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Events', value: stats.events, color: 'text-indigo-600' },
              { label: 'Orders', value: stats.orders, color: 'text-purple-600' },
              { label: 'Users',  value: stats.users,  color: 'text-teal-600' },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 text-center">
                <p className={`text-3xl font-bold tabular-nums ${color}`}>{fmtNum(value)}</p>
                <p className="text-xs text-gray-500 mt-0.5">{label}</p>
              </div>
            ))}
          </div>
        )}

        {isLoading && (
          <div className="grid grid-cols-3 gap-4">
            {[1,2,3].map(i => <div key={i} className="h-24 bg-gray-50 rounded-2xl animate-pulse" />)}
          </div>
        )}

        {/* Export cards */}
        <ExportCard
          dataset="events"
          label="Events"
          description="All track, page, and identify calls"
          rowCount={stats?.events ?? 0}
          oldestEvent={stats?.oldest_event ?? null}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
            </svg>
          }
        />

        <ExportCard
          dataset="orders"
          label="Orders"
          description="E-commerce orders with revenue data"
          rowCount={stats?.orders ?? 0}
          oldestEvent={null}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 00-16.536-1.84M7.5 14.25L5.106 5.272M6 20.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm12.75 0a.75.75 0 11-1.5 0 .75.75 0 011.5 0z" />
            </svg>
          }
        />

        <ExportCard
          dataset="users"
          label="Users"
          description="Identified users with latest traits"
          rowCount={stats?.users ?? 0}
          oldestEvent={null}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
            </svg>
          }
        />

        {/* API info */}
        <div className="bg-gray-900 rounded-2xl border border-gray-700 p-5">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-3">REST API</p>
          <div className="space-y-2 text-xs font-mono text-gray-300">
            <p><span className="text-green-400">GET</span> /api/warehouse/export/events?since=2024-01-01&amp;fmt=csv</p>
            <p><span className="text-green-400">GET</span> /api/warehouse/export/orders?since=2024-01-01&amp;until=2024-12-31</p>
            <p><span className="text-green-400">GET</span> /api/warehouse/export/users?fmt=csv</p>
            <p><span className="text-green-400">GET</span> /api/warehouse/stats</p>
          </div>
          <p className="text-[10px] text-gray-500 mt-3">
            All endpoints require <code className="text-gray-300">Authorization: Bearer &lt;token&gt;</code>.
            Max 500k rows per request — paginate with <code className="text-gray-300">limit</code> + <code className="text-gray-300">offset</code>.
          </p>
        </div>
      </div>
    </AppShell>
  );
}

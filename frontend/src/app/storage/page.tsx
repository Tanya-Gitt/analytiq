'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { type StorageStats, type ArchivedEvent, getStorageStats, archiveEvents, listArchivedEvents } from '@/lib/api';

function fmt(n: number) { return n.toLocaleString(); }

export default function StoragePage() {
  const { data: stats, mutate: reloadStats } = useSWR<StorageStats>('storage/stats', getStorageStats);

  const [days,      setDays]      = useState(90);
  const [archiving, setArchiving] = useState(false);
  const [archiveMsg, setArchiveMsg] = useState<string | null>(null);

  const [search,    setSearch]    = useState('');
  const [query,     setQuery]     = useState('');
  const [archived,  setArchived]  = useState<ArchivedEvent[] | null>(null);
  const [browsing,  setBrowsing]  = useState(false);

  async function handleArchive() {
    if (!confirm(`Archive all events older than ${days} days? They'll move to cold storage and stay queryable.`)) return;
    setArchiving(true);
    setArchiveMsg(null);
    try {
      const res = await archiveEvents(days);
      setArchiveMsg(`Archived ${res.events_archived.toLocaleString()} events older than ${days} days.`);
      await reloadStats();
    } catch {
      setArchiveMsg('Archive failed — try again.');
    } finally {
      setArchiving(false);
    }
  }

  async function handleBrowse() {
    setBrowsing(true);
    try {
      const rows = await listArchivedEvents({ event_name: query || undefined, limit: 100 });
      setArchived(rows);
    } catch {
      setArchived([]);
    } finally {
      setBrowsing(false);
    }
  }

  const hotPct  = stats ? Math.round((stats.hot_events / Math.max(1, stats.total_events)) * 100) : 0;
  const archPct = 100 - hotPct;

  return (
    <AppShell>
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Tiered Storage</h1>
        <p className="text-sm text-gray-500 mt-1">Move old events to cold storage to keep the hot table fast</p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Hot Events',      value: stats ? fmt(stats.hot_events)      : '—', sub: `~${stats?.estimated_hot_mb ?? 0} MB`,    color: 'text-blue-600' },
          { label: 'Archived Events', value: stats ? fmt(stats.archived_events) : '—', sub: `~${stats?.estimated_archive_mb ?? 0} MB`, color: 'text-purple-600' },
          { label: 'Total Events',    value: stats ? fmt(stats.total_events)    : '—', sub: 'across both tiers',                        color: 'text-gray-700' },
        ].map(c => (
          <div key={c.label} className="card text-center space-y-1">
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-sm font-medium text-gray-700">{c.label}</p>
            <p className="text-xs text-gray-400">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* Distribution bar */}
      {stats && stats.total_events > 0 && (
        <div className="card space-y-2">
          <div className="flex justify-between text-xs text-gray-500">
            <span>Hot ({hotPct}%)</span>
            <span>Archived ({archPct}%)</span>
          </div>
          <div className="h-3 rounded-full bg-purple-200 overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full" style={{ width: `${hotPct}%` }} />
          </div>
          <div className="flex justify-between text-xs text-gray-400">
            <span>Oldest hot: {stats.oldest_hot ? new Date(stats.oldest_hot).toLocaleDateString() : '—'}</span>
            <span>Oldest archived: {stats.oldest_archived ? new Date(stats.oldest_archived).toLocaleDateString() : '—'}</span>
          </div>
        </div>
      )}

      {/* Archive action */}
      <div className="card space-y-4">
        <h2 className="font-semibold text-gray-800">Archive Old Events</h2>
        <p className="text-sm text-gray-500">
          Events are moved from the fast <code className="bg-gray-100 px-1 rounded">events</code> table
          to <code className="bg-gray-100 px-1 rounded">archived_events</code>. They remain queryable below.
        </p>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600">Archive events older than</span>
          <select
            className="input w-32"
            value={days}
            onChange={e => setDays(Number(e.target.value))}
          >
            {[7, 14, 30, 60, 90, 180, 365].map(d => (
              <option key={d} value={d}>{d} days</option>
            ))}
          </select>
          <button className="btn-primary" onClick={handleArchive} disabled={archiving}>
            {archiving ? 'Archiving…' : 'Run Archive'}
          </button>
        </div>
        {archiveMsg && (
          <p className="text-sm text-green-700 bg-green-50 border border-green-200 px-3 py-2 rounded-lg">
            {archiveMsg}
          </p>
        )}
      </div>

      {/* Browse archived */}
      <div className="card space-y-4">
        <h2 className="font-semibold text-gray-800">Browse Archived Events</h2>
        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder="Filter by event name (optional)"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { setQuery(search); handleBrowse(); } }}
          />
          <button
            className="btn-primary"
            onClick={() => { setQuery(search); handleBrowse(); }}
            disabled={browsing}
          >
            {browsing ? 'Loading…' : 'Browse'}
          </button>
        </div>

        {archived !== null && (
          archived.length === 0 ? (
            <p className="text-sm text-gray-400">No archived events found.</p>
          ) : (
            <div className="border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-80 overflow-y-auto">
              {archived.map((ev, i) => (
                <div key={i} className="px-4 py-3 flex items-center justify-between text-sm">
                  <div className="space-x-3">
                    <span className="font-mono font-medium">{ev.event_name}</span>
                    {ev.user_id && <span className="text-gray-500 text-xs">{ev.user_id}</span>}
                  </div>
                  <div className="text-xs text-gray-400 space-x-4">
                    <span>received {new Date(ev.received_at).toLocaleDateString()}</span>
                    <span>archived {new Date(ev.archived_at).toLocaleDateString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </div>
    </AppShell>
  );
}

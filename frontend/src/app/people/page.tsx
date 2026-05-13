'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { listPeople, getPerson, type UserProfile, type UserDetail } from '@/lib/api';

// ── helpers ───────────────────────────────────────────────────────────────────

function relTime(iso: string | null) {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function initials(u: UserProfile): string {
  const email = u.traits?.email as string | undefined;
  const name  = u.traits?.name as string | undefined;
  if (name) return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
  if (email) return email[0].toUpperCase();
  return u.user_id.slice(0, 2).toUpperCase();
}

function displayName(u: UserProfile): string {
  return (u.traits?.name as string) || (u.traits?.email as string) || u.user_id;
}

// ── User list item ─────────────────────────────────────────────────────────────

function UserRow({ user, selected, onSelect }: {
  user:     UserProfile;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left px-3 py-2.5 rounded-xl flex items-center gap-3 transition-colors ${
        selected ? 'bg-indigo-50 text-indigo-700' : 'hover:bg-gray-50 text-gray-700'
      }`}
    >
      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
        selected ? 'bg-indigo-200 text-indigo-800' : 'bg-gray-100 text-gray-600'
      }`}>
        {initials(user)}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate">{displayName(user)}</p>
        <p className="text-[10px] text-gray-400 truncate">
          {user.track_events} events · {relTime(user.last_seen)}
        </p>
      </div>
    </button>
  );
}

// ── Traits panel ──────────────────────────────────────────────────────────────

function TraitsPanel({ traits }: { traits: Record<string, unknown> }) {
  const entries = Object.entries(traits);
  if (entries.length === 0) {
    return <p className="text-xs text-gray-400 italic">No traits recorded yet.</p>;
  }
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-2">
      {entries.map(([k, v]) => (
        <div key={k}>
          <p className="text-[10px] text-gray-400 uppercase tracking-wider">{k}</p>
          <p className="text-sm text-gray-800 font-medium truncate">{String(v)}</p>
        </div>
      ))}
    </div>
  );
}

// ── Event timeline ────────────────────────────────────────────────────────────

function EventTimeline({ detail }: { detail: UserDetail }) {
  return (
    <div className="space-y-1">
      {detail.events.map((e, i) => (
        <div key={i} className="flex items-start gap-3 py-1.5 border-b border-gray-50 last:border-0">
          <div className="mt-1 w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-gray-800 truncate">{e.name}</span>
              <span className="text-[10px] text-gray-400 shrink-0">{relTime(e.received_at)}</span>
            </div>
            {Object.keys(e.properties).length > 0 && (
              <p className="text-[10px] text-gray-400 mt-0.5 truncate">
                {Object.entries(e.properties).slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(' · ')}
              </p>
            )}
          </div>
        </div>
      ))}
      {detail.total_events > detail.events.length && (
        <p className="text-[10px] text-gray-400 text-center pt-1">
          Showing {detail.events.length} of {detail.total_events} events
        </p>
      )}
    </div>
  );
}

// ── Profile panel ─────────────────────────────────────────────────────────────

function ProfilePanel({ userId }: { userId: string }) {
  const { data, isLoading } = useSWR(
    ['person', userId],
    () => getPerson(userId, 50, 0),
  );

  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        {[80, 60, 100, 60, 80].map((w, i) => (
          <div key={i} className="h-3 bg-gray-100 rounded animate-pulse" style={{ width: `${w}%` }} />
        ))}
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-4 p-4">
      {/* Avatar + name */}
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-lg font-bold">
          {(data.traits?.name as string)?.[0]?.toUpperCase() ||
           (data.traits?.email as string)?.[0]?.toUpperCase() ||
           data.user_id[0].toUpperCase()}
        </div>
        <div>
          <p className="font-semibold text-gray-900">
            {(data.traits?.name as string) || (data.traits?.email as string) || data.user_id}
          </p>
          <p className="text-xs text-gray-400 font-mono">{data.user_id}</p>
        </div>
      </div>

      {/* Traits */}
      <div className="bg-gray-50 rounded-xl p-3">
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-2">Traits</p>
        <TraitsPanel traits={data.traits} />
      </div>

      {/* Event timeline */}
      <div>
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-2">
          Event History · {data.total_events.toLocaleString()} total
        </p>
        <EventTimeline detail={data} />
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PeoplePage() {
  const [search,      setSearch]      = useState('');
  const [query,       setQuery]       = useState('');
  const [selectedId,  setSelectedId]  = useState<string | null>(null);

  const { data, isLoading } = useSWR(
    ['people', query],
    () => listPeople(query || undefined, 100, 0),
    { refreshInterval: 60_000 },
  );

  const users = data?.users ?? [];

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setQuery(search.trim());
  }

  return (
    <AppShell>
      <div className="max-w-7xl mx-auto flex flex-col gap-4">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">People</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Identified users · traits · event history
            </p>
          </div>
          {data && (
            <span className="text-sm text-gray-400">
              {data.total.toLocaleString()} users
            </span>
          )}
        </div>

        {/* Main layout */}
        <div className="grid grid-cols-[260px_1fr] gap-4 items-start">

          {/* Left: user list */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm flex flex-col" style={{ maxHeight: 'calc(100vh - 140px)' }}>
            {/* Search */}
            <form onSubmit={handleSearch} className="p-3 border-b border-gray-50">
              <div className="flex gap-2">
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search user_id or email…"
                  className="flex-1 text-xs border border-gray-200 rounded-lg px-3 py-1.5
                             focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-gray-50"
                />
                <button type="submit"
                  className="text-xs bg-indigo-600 text-white px-2.5 py-1.5 rounded-lg hover:bg-indigo-700">
                  Go
                </button>
              </div>
            </form>

            {/* List */}
            <div className="overflow-y-auto flex-1 p-2">
              {isLoading && users.length === 0 && (
                <div className="space-y-2 p-2">
                  {[1,2,3,4,5].map(i => <div key={i} className="h-10 bg-gray-50 rounded-xl animate-pulse" />)}
                </div>
              )}
              {!isLoading && users.length === 0 && (
                <div className="text-center py-10 text-gray-400 text-xs">
                  No users identified yet.<br />
                  Call <code className="bg-gray-100 px-1 rounded">Analytics.identify()</code> to start.
                </div>
              )}
              {users.map(u => (
                <UserRow
                  key={u.user_id}
                  user={u}
                  selected={selectedId === u.user_id}
                  onSelect={() => setSelectedId(u.user_id)}
                />
              ))}
            </div>
          </div>

          {/* Right: profile */}
          {!selectedId ? (
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm flex flex-col
                            items-center justify-center py-24 text-gray-400">
              <p className="text-3xl mb-2">👤</p>
              <p className="text-sm font-medium text-gray-600">Select a user to view their profile</p>
              <p className="text-xs text-gray-400 mt-1">
                {users.length > 0
                  ? `${users.length} users loaded`
                  : 'No users yet'}
              </p>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-y-auto"
                 style={{ maxHeight: 'calc(100vh - 140px)' }}>
              <ProfilePanel userId={selectedId} />
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

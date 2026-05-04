'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import RevenueChart from '@/components/charts/RevenueChart';
import TopChannelsChart from '@/components/charts/TopChannelsChart';
import EventsChart from '@/components/charts/EventsChart';
import TopEventsChart from '@/components/charts/TopEventsChart';
import { getSegmentBDashboard, getSegmentADashboard } from '@/lib/api';

const DAYS_OPTIONS = [7, 14, 30, 90];

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function pct(v: number | null) {
  if (v === null) return '—';
  return `${(v * 100).toFixed(1)}%`;
}
function money(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

// ── Segment B ─────────────────────────────────────────────────────────────────

function SegmentBDashboard({ days }: { days: number }) {
  const { data, error, isLoading } = useSWR(
    ['segment-b', days],
    () => getSegmentBDashboard(days),
    { refreshInterval: 60_000 },
  );

  if (isLoading) return <DashboardSkeleton />;
  if (error)     return <ErrorBanner message={error.message} />;
  if (!data)     return null;

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Total Revenue" value={money(data.total_revenue)} sub={`${days}d`} />
        <StatCard label="Orders"        value={data.total_orders.toLocaleString()} />
        <StatCard label="Delivery Rate" value={pct(data.delivery_rate)} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Revenue trend</h3>
          <RevenueChart data={data.revenue_trend} />
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Revenue by channel</h3>
          <TopChannelsChart data={data.top_channels} />
        </div>
      </div>
    </div>
  );
}

// ── Segment A ─────────────────────────────────────────────────────────────────

function SegmentADashboard({ days }: { days: number }) {
  const { data, error, isLoading } = useSWR(
    ['segment-a', days],
    () => getSegmentADashboard(days),
    { refreshInterval: 60_000 },
  );

  if (isLoading) return <DashboardSkeleton />;
  if (error)     return <ErrorBanner message={error.message} />;
  if (!data)     return null;

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4">
        <StatCard label="Total Events" value={data.total_events.toLocaleString()} sub={`${days}d`} />
        <StatCard label="DAU"          value={data.dau !== null ? data.dau.toLocaleString() : '—'} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Events over time</h3>
          <EventsChart data={data.events_timeline} />
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Top events</h3>
          <TopEventsChart data={data.top_events} />
        </div>
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function DashboardSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="grid grid-cols-3 gap-4">
        {[0, 1, 2].map(i => (
          <div key={i} className="card h-20 bg-gray-100" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-6">
        <div className="card h-56 bg-gray-100" />
        <div className="card h-56 bg-gray-100" />
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
      Failed to load dashboard: {message}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Segment = 'B' | 'A';

export default function DashboardPage() {
  const [segment, setSegment] = useState<Segment>('B');
  const [days, setDays] = useState(30);

  return (
    <AppShell>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {segment === 'B' ? 'E-commerce orders & revenue' : 'Product events & engagement'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Segment toggle */}
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {(['B', 'A'] as Segment[]).map(s => (
              <button
                key={s}
                onClick={() => setSegment(s)}
                className={`px-4 py-1.5 text-sm font-medium transition-colors ${
                  segment === s
                    ? 'bg-brand-600 text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-50'
                }`}
              >
                Segment {s}
              </button>
            ))}
          </div>

          {/* Days picker */}
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            className="input w-auto text-sm py-1.5"
          >
            {DAYS_OPTIONS.map(d => (
              <option key={d} value={d}>Last {d} days</option>
            ))}
          </select>
        </div>
      </div>

      {segment === 'B'
        ? <SegmentBDashboard days={days} />
        : <SegmentADashboard days={days} />
      }
    </AppShell>
  );
}

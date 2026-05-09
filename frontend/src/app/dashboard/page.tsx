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

// ── Helpers ───────────────────────────────────────────────────────────────────

function pct(v: number | null) {
  if (v === null) return '—';
  return `${(v * 100).toFixed(1)}%`;
}
function money(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

/** % change from prev to curr; null when prev is 0 (no basis for comparison) */
function changePct(curr: number, prev: number): number | null {
  if (prev === 0) return null;
  return ((curr - prev) / prev) * 100;
}

// ── StatCard ──────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  change?: number | null; // % change vs prior period
}

function StatCard({ label, value, sub, change }: StatCardProps) {
  const hasChange = change !== undefined && change !== null;
  const positive  = hasChange && change! >= 0;

  return (
    <div className="card">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <div className="flex items-end gap-2 mt-1">
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        {hasChange && (
          <span
            className={`text-xs font-semibold mb-0.5 px-1.5 py-0.5 rounded-full ${
              positive
                ? 'bg-green-50 text-green-700'
                : 'bg-red-50 text-red-600'
            }`}
          >
            {positive ? '↑' : '↓'} {Math.abs(change!).toFixed(1)}%
          </span>
        )}
      </div>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

// ── Filter dropdown ───────────────────────────────────────────────────────────

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="input w-auto text-sm py-1.5"
    >
      <option value="">{label}</option>
      {options.map(o => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}

// ── Segment B ─────────────────────────────────────────────────────────────────

function SegmentBDashboard({ days }: { days: number }) {
  const [channel, setChannel] = useState('');

  const { data, error, isLoading } = useSWR(
    ['segment-b', days, channel],
    () => getSegmentBDashboard(days, channel || undefined),
    { refreshInterval: 60_000 },
  );

  if (isLoading) return <DashboardSkeleton cols={3} />;
  if (error)     return <ErrorBanner message={error.message} />;
  if (!data)     return null;

  const revChange   = changePct(data.total_revenue, data.prev_total_revenue);
  const ordChange   = changePct(data.total_orders,  data.prev_total_orders);

  return (
    <div className="space-y-6">
      {/* Filters */}
      {data.available_channels.length > 0 && (
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 font-medium uppercase tracking-wide">Filter:</span>
          <FilterSelect
            label="All channels"
            value={channel}
            options={data.available_channels}
            onChange={setChannel}
          />
          {channel && (
            <button
              onClick={() => setChannel('')}
              className="text-xs text-brand-600 hover:underline"
            >
              Clear
            </button>
          )}
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard
          label="Total Revenue"
          value={money(data.total_revenue)}
          sub={`${days}d`}
          change={revChange}
        />
        <StatCard
          label="Orders"
          value={data.total_orders.toLocaleString()}
          change={ordChange}
        />
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
  const [eventType, setEventType] = useState('');

  const { data, error, isLoading } = useSWR(
    ['segment-a', days, eventType],
    () => getSegmentADashboard(days, eventType || undefined),
    { refreshInterval: 60_000 },
  );

  if (isLoading) return <DashboardSkeleton cols={2} />;
  if (error)     return <ErrorBanner message={error.message} />;
  if (!data)     return null;

  const evtChange = changePct(data.total_events, data.prev_total_events);

  return (
    <div className="space-y-6">
      {/* Filters */}
      {data.available_event_types.length > 0 && (
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 font-medium uppercase tracking-wide">Filter:</span>
          <FilterSelect
            label="All event types"
            value={eventType}
            options={data.available_event_types}
            onChange={setEventType}
          />
          {eventType && (
            <button
              onClick={() => setEventType('')}
              className="text-xs text-brand-600 hover:underline"
            >
              Clear
            </button>
          )}
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4">
        <StatCard
          label="Total Events"
          value={data.total_events.toLocaleString()}
          sub={`${days}d`}
          change={evtChange}
        />
        <StatCard
          label="DAU"
          value={data.dau !== null ? data.dau.toLocaleString() : '—'}
        />
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

// ── Skeletons / errors ────────────────────────────────────────────────────────

function DashboardSkeleton({ cols }: { cols: number }) {
  return (
    <div className="space-y-6 animate-pulse">
      <div className={`grid grid-cols-${cols} gap-4`}>
        {Array.from({ length: cols }).map((_, i) => (
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

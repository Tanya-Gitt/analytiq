'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import RevenueChart from '@/components/charts/RevenueChart';
import TopChannelsChart from '@/components/charts/TopChannelsChart';
import TopProductsChart from '@/components/charts/TopProductsChart';
import AovTrendChart from '@/components/charts/AovTrendChart';
import RevenueByRegionChart from '@/components/charts/RevenueByRegionChart';
import EventsChart from '@/components/charts/EventsChart';
import TopEventsChart from '@/components/charts/TopEventsChart';
import FunnelChart from '@/components/charts/FunnelChart';
import NewVsReturningChart from '@/components/charts/NewVsReturningChart';
import RetentionCohortChart from '@/components/charts/RetentionCohortChart';
import ShareModal from '@/components/ShareModal';
import AnnotationsPanel from '@/components/AnnotationsPanel';
import {
  getSegmentBDashboard, getSegmentADashboard, getRetention,
  listAnnotations, downloadExport, ApiError,
  type Annotation,
} from '@/lib/api';

const DAYS_OPTIONS = [7, 14, 30, 90, 180, 365];

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

function changePct(curr: number, prev: number): number | null {
  if (prev === 0) return null;
  return ((curr - prev) / prev) * 100;
}

// ── StatCard ──────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  change?: number | null;
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
              positive ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'
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

function FilterSelect({ label, value, options, onChange }: {
  label: string; value: string; options: string[]; onChange: (v: string) => void;
}) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} className="input w-auto text-sm py-1.5">
      <option value="">{label}</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

// ── Export button ─────────────────────────────────────────────────────────────

function ExportButton({ segment, days, filter }: {
  segment: 'segment-a' | 'segment-b';
  days: number;
  filter?: { channel?: string; event_type?: string };
}) {
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');

  async function handleExport() {
    setLoading(true); setError('');
    try { await downloadExport(segment, days, filter); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Export failed'); }
    finally { setLoading(false); }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={handleExport} disabled={loading}
        className="flex items-center gap-1.5 text-xs font-medium text-gray-600
                   border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50
                   disabled:opacity-50 transition-colors"
        title="Download as CSV"
      >
        {loading
          ? <span className="w-3.5 h-3.5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          : <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
        }
        Export CSV
      </button>
      {error && <span className="text-xs text-red-500">{error}</span>}
    </div>
  );
}

// ── Segment B ─────────────────────────────────────────────────────────────────

function SegmentBDashboard({ days }: { days: number }) {
  const [channel, setChannel] = useState('');
  const [annotations, setAnnotations] = useState<Annotation[]>([]);

  const { data, error, isLoading } = useSWR(
    ['segment-b', days, channel],
    () => getSegmentBDashboard(days, channel || undefined),
    { refreshInterval: 60_000 },
  );

  // Load annotations once
  useSWR('annotations-B', () => listAnnotations('B'), {
    onSuccess: (data) => setAnnotations(data),
    revalidateOnFocus: false,
  });

  if (isLoading) return <DashboardSkeleton cols={3} />;
  if (error)     return <ErrorBanner message={error.message} />;
  if (!data)     return null;

  const revChange = changePct(data.total_revenue, data.prev_total_revenue);
  const ordChange = changePct(data.total_orders,  data.prev_total_orders);

  return (
    <div className="space-y-6">
      {/* Filters + Export */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {data.available_channels.length > 0 && (
            <>
              <span className="text-xs text-gray-500 font-medium uppercase tracking-wide">Filter:</span>
              <FilterSelect label="All channels" value={channel} options={data.available_channels} onChange={setChannel} />
              {channel && <button onClick={() => setChannel('')} className="text-xs text-brand-600 hover:underline">Clear</button>}
            </>
          )}
        </div>
        <ExportButton segment="segment-b" days={days} filter={channel ? { channel } : undefined} />
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Total Revenue"  value={money(data.total_revenue)} sub={`${days}d`} change={revChange} />
        <StatCard label="Orders"         value={data.total_orders.toLocaleString()} change={ordChange} />
        <StatCard label="Delivery Rate"  value={pct(data.delivery_rate)} />
      </div>

      {/* Revenue trend + annotations */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Revenue trend</h3>
          <RevenueChart data={data.revenue_trend} annotations={annotations} />
          <AnnotationsPanel
            segment="B"
            annotations={annotations}
            onAdd={a => setAnnotations(prev => [...prev, a].sort((x, y) => x.date.localeCompare(y.date)))}
            onDelete={id => setAnnotations(prev => prev.filter(a => a.id !== id))}
          />
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Revenue by channel</h3>
          <TopChannelsChart data={data.top_channels} />
        </div>
      </div>

      {/* Charts row 2 */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Top products</h3>
          <TopProductsChart data={data.top_products} />
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Revenue by region</h3>
          <RevenueByRegionChart data={data.revenue_by_region} />
        </div>
      </div>

      {/* AOV */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">Average order value trend</h3>
        <AovTrendChart data={data.aov_trend} />
      </div>
    </div>
  );
}

// ── Segment A ─────────────────────────────────────────────────────────────────

function SegmentADashboard({ days }: { days: number }) {
  const [eventType, setEventType] = useState('');
  const [retentionWeeks, setRetentionWeeks] = useState(12);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);

  const { data, error, isLoading } = useSWR(
    ['segment-a', days, eventType],
    () => getSegmentADashboard(days, eventType || undefined),
    { refreshInterval: 60_000 },
  );

  const { data: retData, isLoading: retLoading } = useSWR(
    ['retention', retentionWeeks],
    () => getRetention(retentionWeeks),
    { refreshInterval: 300_000 },
  );

  useSWR('annotations-A', () => listAnnotations('A'), {
    onSuccess: (data) => setAnnotations(data),
    revalidateOnFocus: false,
  });

  if (isLoading) return <DashboardSkeleton cols={2} />;
  if (error)     return <ErrorBanner message={error.message} />;
  if (!data)     return null;

  const evtChange = changePct(data.total_events, data.prev_total_events);

  return (
    <div className="space-y-6">
      {/* Filters + Export */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {data.available_event_types.length > 0 && (
            <>
              <span className="text-xs text-gray-500 font-medium uppercase tracking-wide">Filter:</span>
              <FilterSelect label="All event types" value={eventType} options={data.available_event_types} onChange={setEventType} />
              {eventType && <button onClick={() => setEventType('')} className="text-xs text-brand-600 hover:underline">Clear</button>}
            </>
          )}
        </div>
        <ExportButton segment="segment-a" days={days} filter={eventType ? { event_type: eventType } : undefined} />
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4">
        <StatCard label="Total Events" value={data.total_events.toLocaleString()} sub={`${days}d`} change={evtChange} />
        <StatCard label="DAU" value={data.dau !== null ? data.dau.toLocaleString() : '—'} />
      </div>

      {/* Events timeline + annotations */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Events over time</h3>
          <EventsChart data={data.events_timeline} annotations={annotations} />
          <AnnotationsPanel
            segment="A"
            annotations={annotations}
            onAdd={a => setAnnotations(prev => [...prev, a].sort((x, y) => x.date.localeCompare(y.date)))}
            onDelete={id => setAnnotations(prev => prev.filter(a => a.id !== id))}
          />
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Top events</h3>
          <TopEventsChart data={data.top_events} />
        </div>
      </div>

      {/* Charts row 2 */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Conversion funnel</h3>
          <FunnelChart data={data.funnel} filteredBy={eventType || undefined} />
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">New vs returning users</h3>
          <NewVsReturningChart data={data.new_vs_returning} />
        </div>
      </div>

      {/* Retention cohort */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-700">User retention cohorts</h3>
          <select
            value={retentionWeeks}
            onChange={e => setRetentionWeeks(Number(e.target.value))}
            className="input w-auto text-xs py-1"
          >
            {[4, 8, 12, 26, 52].map(w => <option key={w} value={w}>{w} weeks</option>)}
          </select>
        </div>
        {retLoading
          ? <div className="h-32 bg-gray-100 rounded animate-pulse" />
          : retData
            ? <RetentionCohortChart cohorts={retData.cohorts} weeks={retData.weeks} />
            : null
        }
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
  const [customDays, setCustomDays] = useState('');
  const [showCustom, setShowCustom] = useState(false);
  const [showShare, setShowShare] = useState(false);

  function applyCustomDays() {
    const n = parseInt(customDays, 10);
    if (n >= 1 && n <= 365) { setDays(n); setShowCustom(false); setCustomDays(''); }
  }

  return (
    <AppShell>
      {/* Share modal */}
      {showShare && <ShareModal segment={segment} onClose={() => setShowShare(false)} />}

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {segment === 'B' ? 'E-commerce orders & revenue' : 'Product events & engagement'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Share button */}
          <button
            onClick={() => setShowShare(true)}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-600
                       border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50
                       transition-colors"
            title="Share dashboard"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
            </svg>
            Share
          </button>

          {/* Segment toggle */}
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {(['B', 'A'] as Segment[]).map(s => (
              <button
                key={s}
                onClick={() => setSegment(s)}
                className={`px-4 py-1.5 text-sm font-medium transition-colors ${
                  segment === s ? 'bg-brand-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
                }`}
              >
                Segment {s}
              </button>
            ))}
          </div>

          {/* Days picker */}
          <div className="flex items-center gap-2">
            <select
              value={DAYS_OPTIONS.includes(days) ? days : 'custom'}
              onChange={e => {
                if (e.target.value === 'custom') { setShowCustom(true); }
                else { setDays(Number(e.target.value)); setShowCustom(false); }
              }}
              className="input w-auto text-sm py-1.5"
            >
              {DAYS_OPTIONS.map(d => <option key={d} value={d}>Last {d} days</option>)}
              {!DAYS_OPTIONS.includes(days) && <option value="custom">Last {days} days</option>}
              <option value="custom">Custom…</option>
            </select>

            {showCustom && (
              <div className="flex items-center gap-1">
                <input
                  type="number" min={1} max={365}
                  value={customDays} onChange={e => setCustomDays(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && applyCustomDays()}
                  placeholder="days" className="input w-20 text-sm py-1.5" autoFocus
                />
                <button onClick={applyCustomDays} className="btn-primary text-xs px-2 py-1.5">Go</button>
                <button onClick={() => setShowCustom(false)} className="text-xs text-gray-400 hover:text-gray-600">✕</button>
              </div>
            )}
          </div>
        </div>
      </div>

      {segment === 'B' ? <SegmentBDashboard days={days} /> : <SegmentADashboard days={days} />}
    </AppShell>
  );
}

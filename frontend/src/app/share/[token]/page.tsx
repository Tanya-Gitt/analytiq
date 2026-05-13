'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import RevenueChart from '@/components/charts/RevenueChart';
import TopChannelsChart from '@/components/charts/TopChannelsChart';
import TopProductsChart from '@/components/charts/TopProductsChart';
import AovTrendChart from '@/components/charts/AovTrendChart';
import RevenueByRegionChart from '@/components/charts/RevenueByRegionChart';
import EventsChart from '@/components/charts/EventsChart';
import TopEventsChart from '@/components/charts/TopEventsChart';
import FunnelChart from '@/components/charts/FunnelChart';
import NewVsReturningChart from '@/components/charts/NewVsReturningChart';
import { getShareData, type SegmentBDashboard, type SegmentADashboard } from '@/lib/api';

function money(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}
function pct(v: number | null) {
  if (v === null) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

function KPI({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">{title}</h3>
      {children}
    </div>
  );
}

function SegmentBView({ data, days }: { data: SegmentBDashboard; days: number }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <KPI label="Total Revenue" value={money(data.total_revenue)} />
        <KPI label={`Orders (${days}d)`} value={data.total_orders.toLocaleString()} />
        <KPI label="Delivery Rate" value={pct(data.delivery_rate)} />
      </div>
      <div className="grid grid-cols-2 gap-6">
        <Card title="Revenue trend"><RevenueChart data={data.revenue_trend} /></Card>
        <Card title="Revenue by channel"><TopChannelsChart data={data.top_channels} /></Card>
      </div>
      <div className="grid grid-cols-2 gap-6">
        <Card title="Top products"><TopProductsChart data={data.top_products} /></Card>
        <Card title="Revenue by region"><RevenueByRegionChart data={data.revenue_by_region} /></Card>
      </div>
      <Card title="Average order value trend">
        <AovTrendChart data={data.aov_trend} />
      </Card>
    </div>
  );
}

function SegmentAView({ data, days }: { data: SegmentADashboard; days: number }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <KPI label={`Total Events (${days}d)`} value={data.total_events.toLocaleString()} />
        <KPI label="DAU" value={data.dau !== null ? data.dau.toLocaleString() : '—'} />
      </div>
      <div className="grid grid-cols-2 gap-6">
        <Card title="Events over time"><EventsChart data={data.events_timeline} /></Card>
        <Card title="Top events"><TopEventsChart data={data.top_events} /></Card>
      </div>
      <div className="grid grid-cols-2 gap-6">
        <Card title="Conversion funnel"><FunnelChart data={data.funnel} /></Card>
        <Card title="New vs returning users"><NewVsReturningChart data={data.new_vs_returning} /></Card>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

interface SharePayload {
  segment: 'A' | 'B';
  days: number;
  data: SegmentBDashboard | SegmentADashboard;
}

export default function SharePage() {
  const params = useParams();
  const token = params.token as string;

  const [payload, setPayload] = useState<SharePayload | null>(null);
  const [error,   setError]   = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    getShareData(token)
      .then(setPayload)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Minimal navbar */}
      <header className="bg-white border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center">
              <span className="text-white text-xs font-bold">A</span>
            </div>
            <span className="text-sm font-semibold text-gray-700">Analytics</span>
          </div>
          <span className="text-xs text-gray-400 bg-gray-100 px-2.5 py-1 rounded-full">
            Read-only · Public link
          </span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {loading && (
          <div className="flex items-center justify-center h-64">
            <div className="w-8 h-8 border-3 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center">
            <p className="text-lg font-semibold text-red-700 mb-1">Link unavailable</p>
            <p className="text-sm text-red-500">{error}</p>
          </div>
        )}

        {payload && (
          <>
            <div className="mb-6">
              <h1 className="text-xl font-bold text-gray-900">
                {payload.segment === 'B' ? 'Revenue Dashboard' : 'Product Analytics'}
              </h1>
              <p className="text-sm text-gray-500 mt-0.5">
                Last {payload.days} days · Segment {payload.segment}
              </p>
            </div>

            {payload.segment === 'B'
              ? <SegmentBView data={payload.data as SegmentBDashboard} days={payload.days} />
              : <SegmentAView data={payload.data as SegmentADashboard} days={payload.days} />
            }

            <p className="text-center text-xs text-gray-300 mt-12">
              Shared via Analytics Platform · data snapshot from {new Date().toLocaleDateString()}
            </p>
          </>
        )}
      </main>
    </div>
  );
}

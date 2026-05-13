'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { listAnomalies, getAnomalySummary, type AnomalyEvent } from '@/lib/api';

// ── helpers ────────────────────────────────────────────────────────────────────

const METRIC_LABELS: Record<string, string> = {
  event_count_hourly: 'Event Count (hourly)',
  dau_hourly:         'Active Users (hourly)',
  revenue_daily:      'Revenue (daily)',
  order_count_daily:  'Orders (daily)',
};

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function fmt(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}k`;
  return n.toFixed(1);
}

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 60)   return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)   return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ── Summary cards ──────────────────────────────────────────────────────────────

function SummaryCards() {
  const { data } = useSWR('anomaly-summary', getAnomalySummary, { refreshInterval: 30_000 });

  const cards = [
    { label: 'Anomalies (24h)',  value: data?.last_24h    ?? '—', color: 'indigo' },
    { label: 'Anomalies (7d)',   value: data?.last_7d     ?? '—', color: 'violet' },
    { label: 'Critical (24h)',   value: data?.critical_24h ?? '—', color: 'red'   },
    { label: 'Warnings (24h)',   value: data?.warning_24h  ?? '—', color: 'amber' },
  ] as const;

  const colors: Record<string, string> = {
    indigo: 'text-indigo-700 bg-indigo-50 border-indigo-100',
    violet: 'text-violet-700 bg-violet-50 border-violet-100',
    red:    'text-red-600    bg-red-50    border-red-100',
    amber:  'text-amber-600  bg-amber-50  border-amber-100',
  };

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      {cards.map(c => (
        <div key={c.label} className={`rounded-2xl border shadow-sm px-6 py-5 ${colors[c.color]}`}>
          <p className="text-xs font-medium uppercase tracking-widest opacity-70 mb-1">{c.label}</p>
          <p className="text-3xl font-bold tabular-nums">{c.value}</p>
        </div>
      ))}
    </div>
  );
}

// ── Anomaly row ────────────────────────────────────────────────────────────────

function AnomalyRow({ a }: { a: AnomalyEvent }) {
  const isCritical = a.severity === 'critical';
  const pctDiff    = a.baseline > 0
    ? ((a.value - a.baseline) / a.baseline * 100).toFixed(0)
    : null;

  return (
    <div className="flex items-start gap-4 py-4 border-b border-gray-50 last:border-0">
      {/* Severity dot */}
      <div className={`mt-1 w-2.5 h-2.5 rounded-full shrink-0 ${
        isCritical ? 'bg-red-500' : 'bg-amber-400'
      }`} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-gray-800">
            {METRIC_LABELS[a.metric] ?? a.metric}
          </span>
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            isCritical
              ? 'bg-red-100 text-red-700'
              : 'bg-amber-100 text-amber-700'
          }`}>
            {isCritical ? '🔴 Critical' : '🟡 Warning'} {a.z_score > 0 ? '+' : ''}{a.z_score.toFixed(1)}σ
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            a.direction === 'high'
              ? 'bg-red-50 text-red-600'
              : 'bg-blue-50 text-blue-600'
          }`}>
            {a.direction === 'high' ? '↑ Spike' : '↓ Drop'}
          </span>
        </div>

        <div className="mt-1.5 flex items-center gap-3 text-xs text-gray-500 flex-wrap">
          <span>
            Observed: <span className="font-semibold text-gray-700">{fmt(a.value)}</span>
          </span>
          <span>
            Expected: <span className="font-medium text-gray-600">{fmt(a.baseline)}</span>
            {' '}±{fmt(a.std_dev)}
          </span>
          {pctDiff !== null && (
            <span className={a.direction === 'high' ? 'text-red-500' : 'text-blue-500'}>
              {a.direction === 'high' ? '+' : ''}{pctDiff}% vs baseline
            </span>
          )}
        </div>
      </div>

      <div className="shrink-0 text-right">
        <p className="text-xs text-gray-400">{relTime(a.detected_at)}</p>
        <p className="text-xs text-gray-300 mt-0.5">{a.detected_at.slice(0, 16).replace('T', ' ')}</p>
      </div>
    </div>
  );
}

// ── How it works panel ─────────────────────────────────────────────────────────

function HowItWorks() {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-indigo-50 border border-indigo-100 rounded-2xl px-5 py-4">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 text-sm font-semibold text-indigo-700 w-full text-left"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        How anomaly detection works
        <span className="ml-auto text-xs opacity-60">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="mt-3 text-xs text-indigo-700 space-y-1.5 leading-relaxed">
          <p><strong>Baseline:</strong> 28 days of hourly data, bucketed by day-of-week + hour. Monday 14:00 has its own baseline — so a Monday traffic spike isn't confused with a weekend low.</p>
          <p><strong>Detection:</strong> z-score = (current − mean) / std_dev. Warning at ≥3σ, Critical at ≥4σ. Requires ≥4 historical samples in the same slot before firing.</p>
          <p><strong>Cooldown:</strong> Same metric won't re-fire for 6 hours to prevent alert fatigue.</p>
          <p><strong>Runs:</strong> Every hour at :05 past. New orgs build up baselines over 4 weeks.</p>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const METRICS = [
  { value: '',                    label: 'All metrics'   },
  { value: 'event_count_hourly',  label: 'Event count'   },
  { value: 'dau_hourly',          label: 'Active users'  },
  { value: 'revenue_daily',       label: 'Revenue'       },
  { value: 'order_count_daily',   label: 'Orders'        },
];

export default function AnomaliesPage() {
  const [metric, setMetric] = useState('');
  const { data, isLoading, error } = useSWR(
    ['anomalies', metric],
    () => listAnomalies(metric || undefined, 100),
    { refreshInterval: 60_000 },
  );

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Anomaly Detection</h1>
            <p className="mt-0.5 text-sm text-gray-500">
              Statistical baseline · auto-learned per metric, day-of-week, and hour
            </p>
          </div>
          {/* Metric filter */}
          <div className="flex items-center gap-1 bg-gray-100 rounded-xl p-1">
            {METRICS.map(m => (
              <button
                key={m.value}
                onClick={() => setMetric(m.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  metric === m.value
                    ? 'bg-white text-indigo-700 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Summary cards */}
        <SummaryCards />

        {/* How it works */}
        <HowItWorks />

        {/* Anomaly list */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Recent anomalies
            {data && (
              <span className="ml-2 text-xs font-normal text-gray-400">
                {data.length} event{data.length !== 1 ? 's' : ''}
              </span>
            )}
          </h2>

          {isLoading && (
            <div className="flex items-center justify-center h-24 text-sm text-gray-400">
              Loading…
            </div>
          )}
          {error && (
            <div className="text-sm text-red-600 bg-red-50 rounded-xl px-4 py-3">
              {error.message}
            </div>
          )}
          {data && data.length === 0 && (
            <div className="text-center py-12 space-y-2">
              <div className="text-4xl">✅</div>
              <p className="text-sm font-medium text-gray-600">No anomalies detected</p>
              <p className="text-xs text-gray-400">
                The system needs ~4 weeks of data per time-slot to start firing.
                Check back after the baseline matures.
              </p>
            </div>
          )}
          {data && data.length > 0 && (
            <div>
              {data.map(a => <AnomalyRow key={a.id} a={a} />)}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

'use client';

import { useState, useEffect, useCallback } from 'react';
import { getRetention, type RetentionData } from '@/lib/api';
import RetentionCohortChart from '@/components/charts/RetentionCohortChart';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  color = 'indigo',
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: 'indigo' | 'emerald' | 'amber' | 'violet';
}) {
  const ring: Record<string, string> = {
    indigo:  'ring-indigo-100 bg-indigo-50 text-indigo-700',
    emerald: 'ring-emerald-100 bg-emerald-50 text-emerald-700',
    amber:   'ring-amber-100 bg-amber-50 text-amber-700',
    violet:  'ring-violet-100 bg-violet-50 text-violet-700',
  };
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-6 py-5">
      <p className="text-xs font-medium text-gray-400 uppercase tracking-widest mb-1">{label}</p>
      <p className={`text-3xl font-bold tabular-nums ${ring[color].split(' ')[2]}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

// ── Stickiness gauge ──────────────────────────────────────────────────────────

function StickinessCard({
  label,
  value,
  numeratorLabel,
  denominatorLabel,
}: {
  label: string;
  value: number | null;
  numeratorLabel: string;
  denominatorLabel: string;
}) {
  const pct = value != null ? Math.round(value * 100) : null;
  const fill = pct == null ? 0 : Math.min(pct, 100);
  const color =
    pct == null  ? 'text-gray-400' :
    pct >= 20    ? 'text-emerald-600' :
    pct >= 10    ? 'text-amber-600'   : 'text-red-500';

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-6 py-5">
      <p className="text-xs font-medium text-gray-400 uppercase tracking-widest mb-1">{label}</p>
      <p className={`text-3xl font-bold tabular-nums ${color}`}>
        {pct != null ? `${pct}%` : '—'}
      </p>
      <div className="mt-3 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            pct == null ? 'bg-gray-200' :
            pct >= 20   ? 'bg-emerald-500' :
            pct >= 10   ? 'bg-amber-400'   : 'bg-red-400'
          }`}
          style={{ width: `${fill}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-gray-400">{numeratorLabel} ÷ {denominatorLabel}</p>
    </div>
  );
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function RetentionTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-100 shadow-lg rounded-xl px-4 py-2.5 text-sm">
      <p className="font-medium text-gray-700 mb-0.5">Week {label}</p>
      <p className="text-indigo-600 font-semibold tabular-nums">
        {(payload[0].value * 100).toFixed(1)}% avg retained
      </p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const WEEK_OPTIONS = [8, 12, 16, 24] as const;

export default function RetentionPage() {
  const [weeks, setWeeks]   = useState<number>(12);
  const [data, setData]     = useState<RetentionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getRetention(weeks));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load retention data');
    } finally {
      setLoading(false);
    }
  }, [weeks]);

  useEffect(() => { load(); }, [load]);

  const w1avg = data?.avg_by_week.find(w => w.week_number === 1);
  const w4avg = data?.avg_by_week.find(w => w.week_number === 4);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Retention</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Weekly cohort retention · how many users come back after their first visit
          </p>
        </div>

        {/* Week selector */}
        <div className="flex items-center gap-1 bg-gray-100 rounded-xl p-1">
          {WEEK_OPTIONS.map(w => (
            <button
              key={w}
              onClick={() => setWeeks(w)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                weeks === w
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {w}w
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center h-64 text-sm text-gray-400">
          Loading…
        </div>
      )}

      {error && (
        <div className="rounded-xl bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {data && !loading && (
        <>
          {/* Stickiness stats */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            <StatCard
              label="DAU"
              value={data.dau.toLocaleString()}
              sub="Distinct users · last 24 h"
              color="indigo"
            />
            <StatCard
              label="WAU"
              value={data.wau.toLocaleString()}
              sub="Distinct users · last 7 days"
              color="violet"
            />
            <StatCard
              label="MAU"
              value={data.mau.toLocaleString()}
              sub="Distinct users · last 30 days"
              color="emerald"
            />
            <StickinessCard
              label="DAU / WAU"
              value={data.stickiness_dau_wau}
              numeratorLabel="DAU"
              denominatorLabel="WAU"
            />
            <StickinessCard
              label="DAU / MAU"
              value={data.stickiness_dau_mau}
              numeratorLabel="DAU"
              denominatorLabel="MAU"
            />
          </div>

          {/* Retention summary row */}
          {(w1avg || w4avg) && (
            <div className="grid grid-cols-2 gap-4">
              {w1avg && (
                <StatCard
                  label="Avg Week-1 Retention"
                  value={`${(w1avg.avg_pct * 100).toFixed(1)}%`}
                  sub="Users who came back 1 week after sign-up"
                  color="indigo"
                />
              )}
              {w4avg && (
                <StatCard
                  label="Avg Week-4 Retention"
                  value={`${(w4avg.avg_pct * 100).toFixed(1)}%`}
                  sub="Users who came back 4 weeks after sign-up"
                  color="amber"
                />
              )}
            </div>
          )}

          {/* Average retention curve */}
          {data.avg_by_week.length > 1 && (
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
              <h2 className="text-sm font-semibold text-gray-700 mb-4">
                Average Retention Curve
                <span className="ml-2 text-xs font-normal text-gray-400">
                  — across all {data.cohorts.length} cohort{data.cohorts.length !== 1 ? 's' : ''}
                </span>
              </h2>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart
                  data={data.avg_by_week}
                  margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                  <XAxis
                    dataKey="week_number"
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    tickFormatter={v => `Wk ${v}`}
                  />
                  <YAxis
                    tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    domain={[0, 1]}
                    width={42}
                  />
                  <Tooltip content={<RetentionTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="avg_pct"
                    stroke="#6366f1"
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: '#6366f1' }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Cohort grid */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">
              Weekly Cohort Grid
            </h2>
            <p className="text-xs text-gray-400 mb-4">
              Each row = users whose first event was in that week. Each cell = % who returned in week N.
            </p>
            <RetentionCohortChart cohorts={data.cohorts} weeks={data.weeks} />
          </div>
        </>
      )}
    </div>
  );
}

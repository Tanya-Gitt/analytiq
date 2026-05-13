'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { getChurnSummary, listChurn, type ChurnUser, type RiskLevel, type ChurnSummary } from '@/lib/api';

// ── helpers ───────────────────────────────────────────────────────────────────

function relTime(iso: string | null) {
  if (!iso) return '—';
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (d === 0) return 'today';
  if (d === 1) return 'yesterday';
  return `${d}d ago`;
}

function displayName(u: ChurnUser): string {
  return (u.traits?.name as string) || (u.traits?.email as string) || u.user_id;
}

// ── Risk badge ────────────────────────────────────────────────────────────────

const RISK_CONFIG: Record<RiskLevel, { label: string; bg: string; text: string; dot: string }> = {
  healthy:  { label: 'Healthy',   bg: 'bg-green-50',  text: 'text-green-700',  dot: 'bg-green-500'  },
  warning:  { label: 'Warning',   bg: 'bg-yellow-50', text: 'text-yellow-700', dot: 'bg-yellow-500' },
  at_risk:  { label: 'At Risk',   bg: 'bg-orange-50', text: 'text-orange-700', dot: 'bg-orange-500' },
  critical: { label: 'Critical',  bg: 'bg-red-50',    text: 'text-red-700',    dot: 'bg-red-500'    },
};

function RiskBadge({ level }: { level: RiskLevel }) {
  const c = RISK_CONFIG[level];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${c.bg} ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}

// ── Risk score bar ────────────────────────────────────────────────────────────

function ScoreBar({ score }: { score: number }) {
  const color = score >= 70 ? 'bg-red-500' : score >= 40 ? 'bg-orange-400' : score >= 20 ? 'bg-yellow-400' : 'bg-green-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs text-gray-500 tabular-nums w-6">{score}</span>
    </div>
  );
}

// ── Summary cards ─────────────────────────────────────────────────────────────

function SummaryCards({ summary }: { summary: ChurnSummary }) {
  const levels: { key: keyof ChurnSummary; label: string; desc: string }[] = [
    { key: 'healthy',  label: 'Healthy',  desc: 'Active in last 7d'   },
    { key: 'warning',  label: 'Warning',  desc: '7–14 days inactive'  },
    { key: 'at_risk',  label: 'At Risk',  desc: '14–30 days inactive' },
    { key: 'critical', label: 'Critical', desc: '30+ days inactive'   },
  ];
  const c: Record<string, string> = {
    healthy:  'border-green-100  bg-green-50  text-green-700',
    warning:  'border-yellow-100 bg-yellow-50 text-yellow-700',
    at_risk:  'border-orange-100 bg-orange-50 text-orange-700',
    critical: 'border-red-100   bg-red-50    text-red-700',
  };
  return (
    <div className="grid grid-cols-4 gap-4">
      {levels.map(({ key, label, desc }) => (
        <div key={key} className={`rounded-2xl border p-4 ${c[key as string]}`}>
          <p className="text-3xl font-bold tabular-nums">{(summary[key as keyof ChurnSummary] as number).toLocaleString()}</p>
          <p className="text-sm font-semibold mt-0.5">{label}</p>
          <p className="text-xs opacity-75 mt-0.5">{desc}</p>
        </div>
      ))}
    </div>
  );
}

// ── User table ────────────────────────────────────────────────────────────────

function UserTable({ users }: { users: ChurnUser[] }) {
  if (users.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400 text-sm">
        No users match this filter.
      </div>
    );
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-gray-100">
          {['User', 'Risk', 'Score', 'Last Seen', 'Events (7d)', 'Events (30d)'].map(h => (
            <th key={h} className="text-left text-[10px] font-semibold text-gray-400 uppercase tracking-widest pb-2 pr-4">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-50">
        {users.map(u => (
          <tr key={u.user_id} className="hover:bg-gray-50/50 transition-colors">
            <td className="py-2.5 pr-4">
              <p className="font-medium text-gray-800 truncate max-w-[160px]">{displayName(u)}</p>
              <p className="text-[10px] text-gray-400 font-mono truncate max-w-[160px]">{u.user_id}</p>
            </td>
            <td className="py-2.5 pr-4"><RiskBadge level={u.risk_level} /></td>
            <td className="py-2.5 pr-4 w-32"><ScoreBar score={u.risk_score} /></td>
            <td className="py-2.5 pr-4 text-gray-600">{relTime(u.last_seen)}</td>
            <td className="py-2.5 pr-4 tabular-nums text-gray-600">{u.events_7d.toLocaleString()}</td>
            <td className="py-2.5 tabular-nums text-gray-600">{u.events_30d.toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const FILTERS: { key: RiskLevel | 'all'; label: string }[] = [
  { key: 'all',      label: 'All' },
  { key: 'critical', label: 'Critical' },
  { key: 'at_risk',  label: 'At Risk' },
  { key: 'warning',  label: 'Warning' },
  { key: 'healthy',  label: 'Healthy' },
];

export default function ChurnPage() {
  const [filter, setFilter] = useState<RiskLevel | 'all'>('all');

  const { data: summary } = useSWR('churn-summary', getChurnSummary, { refreshInterval: 60_000 });
  const { data: users, isLoading } = useSWR(
    ['churn', filter],
    () => listChurn(filter === 'all' ? undefined : filter, 200),
    { refreshInterval: 60_000 },
  );

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto flex flex-col gap-6">

        {/* Header */}
        <div>
          <h1 className="text-xl font-bold text-gray-900">Churn Prediction</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Users ranked by inactivity · risk scores based on recency + activity
          </p>
        </div>

        {/* Summary cards */}
        {summary ? (
          <SummaryCards summary={summary} />
        ) : (
          <div className="grid grid-cols-4 gap-4">
            {[1,2,3,4].map(i => <div key={i} className="h-24 bg-gray-50 rounded-2xl animate-pulse" />)}
          </div>
        )}

        {/* Risk distribution bar */}
        {summary && summary.total > 0 && (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">Risk Distribution</p>
            <div className="flex h-5 rounded-full overflow-hidden gap-0.5">
              {(['healthy', 'warning', 'at_risk', 'critical'] as RiskLevel[]).map(level => {
                const pct = ((summary[level as keyof ChurnSummary] as number) / summary.total) * 100;
                if (pct === 0) return null;
                const colors: Record<RiskLevel, string> = {
                  healthy: 'bg-green-400', warning: 'bg-yellow-400',
                  at_risk: 'bg-orange-400', critical: 'bg-red-500',
                };
                return (
                  <div
                    key={level}
                    className={`${colors[level]} transition-all`}
                    style={{ width: `${pct}%` }}
                    title={`${RISK_CONFIG[level].label}: ${pct.toFixed(1)}%`}
                  />
                );
              })}
            </div>
            <div className="flex gap-4 mt-2">
              {(['healthy', 'warning', 'at_risk', 'critical'] as RiskLevel[]).map(level => (
                <div key={level} className="flex items-center gap-1">
                  <div className={`w-2 h-2 rounded-full ${RISK_CONFIG[level].dot}`} />
                  <span className="text-[10px] text-gray-500">
                    {RISK_CONFIG[level].label} ({(((summary[level as keyof ChurnSummary] as number) / summary.total) * 100).toFixed(0)}%)
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* User table */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm">
          {/* Filter tabs */}
          <div className="flex gap-1 p-3 border-b border-gray-50">
            {FILTERS.map(f => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  filter === f.key
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-500 hover:bg-gray-100'
                }`}
              >
                {f.label}
                {f.key !== 'all' && summary && (
                  <span className="ml-1 opacity-70">
                    {summary[f.key as keyof ChurnSummary]}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="p-4">
            {isLoading ? (
              <div className="space-y-2">
                {[1,2,3,4,5].map(i => <div key={i} className="h-10 bg-gray-50 rounded animate-pulse" />)}
              </div>
            ) : (
              <UserTable users={users ?? []} />
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

'use client';

import { useState, useMemo } from 'react';
import AppShell from '@/components/layout/AppShell';

const CATEGORIES = [
  { value: '',          label: 'All' },
  { value: 'flag',      label: 'Flags' },
  { value: 'team',      label: 'Team' },
  { value: 'connector', label: 'Connectors' },
  { value: 'gdpr',      label: 'GDPR' },
  { value: 'alert',     label: 'Alerts' },
];

const ACTION_COLORS: Record<string, string> = {
  'flag.created':           'bg-green-100 text-green-700',
  'flag.updated':           'bg-blue-100 text-blue-700',
  'flag.deleted':           'bg-red-100 text-red-700',
  'member.invited':         'bg-green-100 text-green-700',
  'member.removed':         'bg-red-100 text-red-700',
  'member.role_changed':    'bg-yellow-100 text-yellow-700',
  'connector.created':      'bg-green-100 text-green-700',
  'connector.deleted':      'bg-red-100 text-red-700',
  'gdpr.export':            'bg-blue-100 text-blue-700',
  'gdpr.forget':            'bg-red-100 text-red-700',
  'gdpr.opt_out':           'bg-orange-100 text-orange-700',
  'gdpr.opt_out_removed':   'bg-gray-100 text-gray-700',
  'alert.created':          'bg-green-100 text-green-700',
  'alert.deleted':          'bg-red-100 text-red-700',
  'storage.archive':        'bg-purple-100 text-purple-700',
};

// ── Static demo audit entries ─────────────────────────────────────────────────
//
// The audit log table is empty in the seeded org (the seeder only writes
// events + orders, not audit rows). To showcase the feature for demo visitors
// we render a plausible 30-day history of admin activity here.

interface AuditEntry {
  id:            string;
  created_at:    string;
  actor_email:   string | null;
  action:        string;
  category:      string;
  resource_type: string | null;
  metadata:      Record<string, unknown>;
}

const STATIC_ENTRIES: AuditEntry[] = (() => {
  const now = Date.now();
  const min = 60_000;
  const hr  = 60 * min;
  const day = 24 * hr;
  const t = (offset: number) => new Date(now - offset).toISOString();

  return [
    { id: '1',  created_at: t(8 * min),       actor_email: 'avery@acmehq.io',      action: 'flag.updated',         category: 'flag',      resource_type: 'feature_flag', metadata: { flag: 'new_checkout_v2', rollout_pct: 50 } },
    { id: '2',  created_at: t(42 * min),      actor_email: 'priya@acmehq.io',      action: 'alert.created',        category: 'alert',     resource_type: 'alert',        metadata: { name: 'High error rate', channel: 'slack' } },
    { id: '3',  created_at: t(2 * hr),        actor_email: 'avery@acmehq.io',      action: 'connector.created',    category: 'connector', resource_type: 'connector',    metadata: { type: 'webhook', target: 'hooks.slack.com' } },
    { id: '4',  created_at: t(3 * hr),        actor_email: 'priya@acmehq.io',      action: 'gdpr.export',          category: 'gdpr',      resource_type: 'user',         metadata: { user_id: 'usr_regular_065', format: 'json' } },
    { id: '5',  created_at: t(5 * hr),        actor_email: 'demo@analytiq.io',     action: 'member.invited',       category: 'team',      resource_type: 'member',       metadata: { invited: 'jordan@acmehq.io', role: 'analyst' } },
    { id: '6',  created_at: t(8 * hr),        actor_email: 'avery@acmehq.io',      action: 'flag.created',         category: 'flag',      resource_type: 'feature_flag', metadata: { flag: 'dark_mode_beta', rollout_pct: 10 } },
    { id: '7',  created_at: t(14 * hr),       actor_email: 'jordan@acmehq.io',     action: 'storage.archive',      category: 'storage',   resource_type: 'event',        metadata: { older_than: '90d', rows: 1284039 } },
    { id: '8',  created_at: t(1 * day),       actor_email: 'priya@acmehq.io',      action: 'alert.created',        category: 'alert',     resource_type: 'alert',        metadata: { name: 'Revenue drop > 20%', channel: 'email' } },
    { id: '9',  created_at: t(1 * day + 3 * hr),  actor_email: 'avery@acmehq.io',  action: 'gdpr.opt_out',         category: 'gdpr',      resource_type: 'user',         metadata: { user_id: 'usr_occasional_016' } },
    { id: '10', created_at: t(1 * day + 7 * hr),  actor_email: 'demo@analytiq.io', action: 'member.role_changed', category: 'team',      resource_type: 'member',       metadata: { member: 'jordan@acmehq.io', from: 'analyst', to: 'admin' } },
    { id: '11', created_at: t(2 * day),       actor_email: 'priya@acmehq.io',      action: 'flag.updated',         category: 'flag',      resource_type: 'feature_flag', metadata: { flag: 'new_checkout_v2', rollout_pct: 25 } },
    { id: '12', created_at: t(2 * day + 5 * hr),  actor_email: 'avery@acmehq.io',  action: 'connector.created',    category: 'connector', resource_type: 'connector',    metadata: { type: 'segment', target: 'cdp.segment.com' } },
    { id: '13', created_at: t(3 * day),       actor_email: 'jordan@acmehq.io',     action: 'gdpr.forget',          category: 'gdpr',      resource_type: 'user',         metadata: { user_id: 'usr_churned_002', records_deleted: 412 } },
    { id: '14', created_at: t(3 * day + 6 * hr),  actor_email: 'demo@analytiq.io', action: 'alert.deleted',        category: 'alert',     resource_type: 'alert',        metadata: { name: 'Old test alert' } },
    { id: '15', created_at: t(4 * day),       actor_email: 'avery@acmehq.io',      action: 'flag.created',         category: 'flag',      resource_type: 'feature_flag', metadata: { flag: 'pricing_v3', rollout_pct: 0 } },
    { id: '16', created_at: t(5 * day),       actor_email: 'priya@acmehq.io',      action: 'connector.deleted',    category: 'connector', resource_type: 'connector',    metadata: { type: 'webhook', target: 'old-endpoint.example.com' } },
    { id: '17', created_at: t(6 * day),       actor_email: 'demo@analytiq.io',     action: 'member.invited',       category: 'team',      resource_type: 'member',       metadata: { invited: 'priya@acmehq.io', role: 'admin' } },
    { id: '18', created_at: t(7 * day),       actor_email: 'avery@acmehq.io',      action: 'gdpr.opt_out_removed', category: 'gdpr',      resource_type: 'user',         metadata: { user_id: 'usr_regular_113' } },
    { id: '19', created_at: t(9 * day),       actor_email: 'avery@acmehq.io',      action: 'flag.deleted',         category: 'flag',      resource_type: 'feature_flag', metadata: { flag: 'deprecated_onboarding_v1' } },
    { id: '20', created_at: t(11 * day),      actor_email: 'demo@analytiq.io',     action: 'connector.created',    category: 'connector', resource_type: 'connector',    metadata: { type: 'bigquery', target: 'analytics-prod.events' } },
    { id: '21', created_at: t(14 * day),      actor_email: 'priya@acmehq.io',      action: 'alert.created',        category: 'alert',     resource_type: 'alert',        metadata: { name: 'DAU anomaly', channel: 'pagerduty' } },
    { id: '22', created_at: t(18 * day),      actor_email: 'demo@analytiq.io',     action: 'member.removed',       category: 'team',      resource_type: 'member',       metadata: { removed: 'former-intern@acmehq.io' } },
    { id: '23', created_at: t(22 * day),      actor_email: 'avery@acmehq.io',      action: 'storage.archive',      category: 'storage',   resource_type: 'event',        metadata: { older_than: '180d', rows: 4827193 } },
    { id: '24', created_at: t(28 * day),      actor_email: 'demo@analytiq.io',     action: 'flag.created',         category: 'flag',      resource_type: 'feature_flag', metadata: { flag: 'new_checkout_v2', rollout_pct: 5 } },
  ];
})();

const PAGE_SIZE = 25;

export default function AuditPage() {
  const [category, setCategory] = useState('');
  const [offset,   setOffset]   = useState(0);

  const filtered = useMemo(
    () => category ? STATIC_ENTRIES.filter(e => e.category === category) : STATIC_ENTRIES,
    [category],
  );

  const entries = filtered.slice(offset, offset + PAGE_SIZE);
  const total   = filtered.length;
  const pages   = Math.ceil(total / PAGE_SIZE);
  const current = Math.floor(offset / PAGE_SIZE);

  function changeCategory(cat: string) {
    setCategory(cat);
    setOffset(0);
  }

  return (
    <AppShell>
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Audit Log</h1>
        <p className="text-sm text-gray-500 mt-1">All admin actions across your organisation</p>
      </div>

      {/* Demo-data disclaimer */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5 flex gap-2.5">
        <span className="text-amber-600 text-sm shrink-0 mt-0.5">ℹ️</span>
        <div className="text-[11px] text-amber-900 leading-relaxed">
          <p className="font-semibold mb-0.5">Sample audit history</p>
          <p className="text-amber-800">
            The seeded demo org has no real admin activity, so this view shows a
            representative 30-day log of flag changes, team edits, GDPR
            requests, connector setup, and alert configuration. In production
            every privileged action is automatically captured here.
          </p>
        </div>
      </div>

      {/* Category filter */}
      <div className="flex gap-2 flex-wrap">
        {CATEGORIES.map(c => (
          <button
            key={c.value}
            onClick={() => changeCategory(c.value)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              category === c.value
                ? 'bg-brand-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {c.label}
          </button>
        ))}
        {total > 0 && (
          <span className="ml-auto text-sm text-gray-400 self-center">
            {total.toLocaleString()} total entries
          </span>
        )}
      </div>

      {/* Log table */}
      <div className="card p-0 overflow-hidden">
        {entries.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-400">No audit entries yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Time</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Actor</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Action</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Resource</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {entries.map(e => (
                <tr key={e.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">
                    {new Date(e.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-gray-700 font-medium max-w-[160px] truncate">
                    {e.actor_email ?? '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${ACTION_COLORS[e.action] ?? 'bg-gray-100 text-gray-700'}`}>
                      {e.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {e.resource_type && (
                      <span>{e.resource_type}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs max-w-[200px]">
                    {Object.keys(e.metadata).length > 0 && (
                      <span className="font-mono">
                        {Object.entries(e.metadata)
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(' · ')}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between">
          <button
            className="btn-secondary"
            disabled={current === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span className="text-sm text-gray-500">
            Page {current + 1} of {pages}
          </span>
          <button
            className="btn-secondary"
            disabled={current >= pages - 1}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      )}
    </div>
    </AppShell>
  );
}

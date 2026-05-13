'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { type AuditPage, listAudit } from '@/lib/api';

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

const PAGE_SIZE = 25;

export default function AuditPage() {
  const [category, setCategory] = useState('');
  const [offset,   setOffset]   = useState(0);

  const fetcher = () => listAudit({ category: category || undefined, limit: PAGE_SIZE, offset });
  const { data } = useSWR<AuditPage>(['audit', category, offset], fetcher);

  const entries = data?.entries ?? [];
  const total   = data?.total   ?? 0;
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

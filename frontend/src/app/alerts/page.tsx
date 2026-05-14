'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import {
  listAlertRules, createAlertRule, deleteAlertRule,
  AlertRule, ApiError,
} from '@/lib/api';
import ConfirmDialog from '@/components/ConfirmDialog';

// ── Available metrics ─────────────────────────────────────────────────────────

const METRICS = [
  { value: 'revenue_total',   label: 'Revenue (total $)',    segment: 'B' },
  { value: 'order_count',     label: 'Order count',          segment: 'B' },
  { value: 'delivery_rate',   label: 'Delivery rate (0–1)',  segment: 'B' },
  { value: 'avg_order_value', label: 'Avg order value ($)',  segment: 'B' },
  { value: 'event_count',     label: 'Event count',          segment: 'A' },
  { value: 'dau',             label: 'Daily active users',   segment: 'A' },
];

// ── Create alert rule form ────────────────────────────────────────────────────

function CreateAlertForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [metric, setMetric] = useState('order_count');
  const [condition, setCondition] = useState('below');
  const [threshold, setThreshold] = useState('');
  const [windowHours, setWindowHours] = useState('24');
  const [channel, setChannel] = useState('slack');
  const [destination, setDestination] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleCreate() {
    setError('');
    setLoading(true);
    try {
      await createAlertRule({
        name,
        metric,
        condition,
        threshold: condition !== 'no_data' ? Number(threshold) : undefined,
        window_hours: Number(windowHours),
        channel,
        destination,
      });
      onCreated();
      setOpen(false);
      setName(''); setThreshold(''); setDestination('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn-primary">
        + New alert rule
      </button>
    );
  }

  return (
    <div className="card space-y-4 max-w-lg">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">New alert rule</h3>
        <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div>
        <label className="label">Rule name</label>
        <input className="input" placeholder="Revenue dropped below threshold"
          value={name} onChange={e => setName(e.target.value)} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Metric</label>
          <select value={metric} onChange={e => setMetric(e.target.value)} className="input">
            {METRICS.map(m => (
              <option key={m.value} value={m.value}>{m.label} (Seg {m.segment})</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Window</label>
          <select value={windowHours} onChange={e => setWindowHours(e.target.value)} className="input">
            <option value="1">Last 1 hour</option>
            <option value="6">Last 6 hours</option>
            <option value="24">Last 24 hours</option>
            <option value="72">Last 3 days</option>
            <option value="168">Last 7 days</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Condition</label>
          <select value={condition} onChange={e => setCondition(e.target.value)} className="input">
            <option value="below">below threshold</option>
            <option value="above">above threshold</option>
            <option value="no_data">no data</option>
          </select>
        </div>
        {condition !== 'no_data' && (
          <div>
            <label className="label">Threshold</label>
            <input className="input" type="number" step="any"
              placeholder="e.g. 1000"
              value={threshold} onChange={e => setThreshold(e.target.value)} />
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Channel</label>
          <select value={channel} onChange={e => setChannel(e.target.value)} className="input">
            <option value="slack">Slack</option>
            <option value="email">Email</option>
          </select>
        </div>
        <div>
          <label className="label">
            {channel === 'slack' ? 'Webhook URL' : 'Email address'}
          </label>
          <input className="input"
            placeholder={channel === 'slack' ? 'https://hooks.slack.com/…' : 'alerts@company.com'}
            value={destination} onChange={e => setDestination(e.target.value)} />
        </div>
      </div>

      <div className="flex gap-2 justify-end pt-1">
        <button onClick={() => setOpen(false)} className="btn-secondary">Cancel</button>
        <button onClick={handleCreate} className="btn-primary" disabled={loading}>
          {loading ? 'Creating…' : 'Create rule'}
        </button>
      </div>
    </div>
  );
}

// ── Alert rule row ────────────────────────────────────────────────────────────

function AlertRuleRow({
  rule,
  onDeleted,
}: {
  rule: AlertRule;
  onDeleted: () => void;
}) {
  const [deleting,     setDeleting]     = useState(false);
  const [confirmOpen,  setConfirmOpen]  = useState(false);

  async function doDelete() {
    setDeleting(true);
    try {
      await deleteAlertRule(rule.id);
      onDeleted();
    } finally {
      setDeleting(false);
    }
  }

  const conditionStr =
    rule.condition === 'no_data'
      ? 'no data'
      : `${rule.condition} ${rule.threshold}`;

  return (
    <>
      <div className="card flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm text-gray-900">{rule.name}</span>
            <span className={rule.state === 'OK' ? 'badge-ok' : 'badge-triggered'}>
              {rule.state}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">
            <span className="font-mono">{rule.metric}</span>
            {' '}{conditionStr}
            {' '}over last {rule.window_hours}h
            {' '}→ {rule.channel}: {rule.destination}
          </p>
          {rule.last_triggered_at && (
            <p className="text-xs text-gray-400 mt-0.5">
              Last triggered: {new Date(rule.last_triggered_at).toLocaleString()}
            </p>
          )}
        </div>
        <button
          onClick={() => setConfirmOpen(true)}
          disabled={deleting}
          className="text-xs text-red-500 hover:text-red-700 flex-shrink-0 disabled:opacity-50"
        >
          {deleting ? 'Deleting…' : 'Delete'}
        </button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title={`Delete rule "${rule.name}"?`}
        description="This alert rule will be permanently removed and you will stop receiving notifications."
        confirmLabel="Delete"
        onConfirm={doDelete}
        onClose={() => setConfirmOpen(false)}
      />
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  const { data, isLoading, error, mutate: revalidate } = useSWR(
    'alerts',
    listAlertRules,
    { refreshInterval: 30_000 },
  );

  return (
    <AppShell>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Alert Rules</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Get notified on Slack or email when metrics cross thresholds
          </p>
        </div>
        <CreateAlertForm onCreated={() => revalidate()} />
      </div>

      {isLoading && (
        <div className="space-y-3 animate-pulse">
          {[0, 1, 2].map(i => <div key={i} className="card h-16 bg-gray-100" />)}
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error.message}
        </div>
      )}

      {data && data.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg">No alert rules yet</p>
          <p className="text-sm mt-1">Create one above to start monitoring your metrics</p>
        </div>
      )}

      <div className="space-y-3">
        {data?.map(rule => (
          <AlertRuleRow key={rule.id} rule={rule} onDeleted={() => revalidate()} />
        ))}
      </div>

      {/* Info box */}
      {data && data.length > 0 && (
        <div className="mt-8 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-sm text-blue-700">
          <strong>How alerts work:</strong> The scheduler evaluates all rules every 60 seconds.
          Triggered → sends notification once. Stays triggered → re-fires after 24 hours.
          Resolves → sends a "resolved" notification.
        </div>
      )}
    </AppShell>
  );
}

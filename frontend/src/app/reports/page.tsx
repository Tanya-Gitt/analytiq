'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { authHeader } from '@/lib/auth';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';
const req = (url: string) => fetch(`${BASE}${url}`, { headers: authHeader() }).then(r => r.json());

interface Report {
  id:          string;
  name:        string;
  metric:      string;
  period:      string;
  recipients:  string[];
  enabled:     boolean;
  last_run_at: string | null;
  created_at:  string;
}

const METRICS = ['events_count','revenue_total','dau','new_users','churn_count'] as const;
const PERIODS  = ['daily','weekly','monthly'] as const;

const PERIOD_COLORS: Record<string,string> = {
  daily:   'bg-blue-100 text-blue-700',
  weekly:  'bg-purple-100 text-purple-700',
  monthly: 'bg-green-100 text-green-700',
};

const METRIC_LABELS: Record<string,string> = {
  events_count:  'Event Count',
  revenue_total: 'Total Revenue',
  dau:           'Daily Active Users',
  new_users:     'New Users',
  churn_count:   'At-Risk Users',
};

export default function ReportsPage() {
  const { data: reports = [], mutate } = useSWR<Report[]>('/reports', req);

  const [showAdd,     setShowAdd]     = useState(false);
  const [name,        setName]        = useState('');
  const [metric,      setMetric]      = useState<string>('events_count');
  const [period,      setPeriod]      = useState<string>('weekly');
  const [recipients,  setRecipients]  = useState('');
  const [enabled,     setEnabled]     = useState(true);
  const [saving,      setSaving]      = useState(false);
  const [runResult,   setRunResult]   = useState<{id:string;metric:string;sent_to:string[]}|null>(null);
  const [msg,         setMsg]         = useState<{text:string;ok:boolean}|null>(null);

  function flash(text: string, ok: boolean) {
    setMsg({text, ok}); setTimeout(() => setMsg(null), 4000);
  }

  async function handleCreate() {
    if (!name.trim() || !recipients.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${BASE}/reports`, {
        method: 'POST',
        headers: {'Content-Type':'application/json',...authHeader()},
        body: JSON.stringify({
          name: name.trim(),
          metric,
          period,
          recipients: recipients.split(',').map(s => s.trim()).filter(Boolean),
          enabled,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      await mutate();
      setShowAdd(false);
      setName(''); setRecipients('');
      flash('Report created', true);
    } catch (e) { flash(e instanceof Error ? e.message : 'Error', false); }
    finally { setSaving(false); }
  }

  async function toggleEnabled(r: Report) {
    await fetch(`${BASE}/reports/${r.id}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json',...authHeader()},
      body: JSON.stringify({enabled: !r.enabled}),
    });
    await mutate();
  }

  async function handleDelete(r: Report) {
    if (!confirm(`Delete report "${r.name}"?`)) return;
    await fetch(`${BASE}/reports/${r.id}`, {method:'DELETE', headers: authHeader()});
    await mutate();
    flash('Report deleted', true);
  }

  async function handleRun(r: Report) {
    const res = await fetch(`${BASE}/reports/${r.id}/run`, {method:'POST', headers: authHeader()});
    const data = await res.json();
    setRunResult({id: r.id, metric: data.metric, sent_to: data.sent_to});
    await mutate();
  }

  return (
    <AppShell>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Scheduled Reports</h1>
            <p className="text-sm text-gray-500 mt-1">Automated metric digests sent to your team</p>
          </div>
          <button className="btn-primary" onClick={() => setShowAdd(true)}>+ Add Report</button>
        </div>

        {msg && (
          <div className={`px-4 py-3 rounded-lg text-sm font-medium ${msg.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {msg.text}
          </div>
        )}

        {runResult && (
          <div className="card border-green-200 bg-green-50 space-y-1">
            <p className="text-sm font-medium text-green-800">Report sent: <strong>{runResult.metric}</strong></p>
            <p className="text-xs text-green-700">Recipients: {runResult.sent_to.join(', ') || 'none (email delivery failed)'}</p>
            <button className="text-xs text-green-600 underline" onClick={() => setRunResult(null)}>Dismiss</button>
          </div>
        )}

        {showAdd && (
          <div className="card space-y-4 border-brand-200">
            <h3 className="font-semibold text-gray-800">New Report</h3>
            <input className="input w-full" placeholder="Report name" value={name} onChange={e => setName(e.target.value)} />
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Metric</label>
                <select className="input w-full" value={metric} onChange={e => setMetric(e.target.value)}>
                  {METRICS.map(m => <option key={m} value={m}>{METRIC_LABELS[m]}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Period</label>
                <select className="input w-full" value={period} onChange={e => setPeriod(e.target.value)}>
                  {PERIODS.map(p => <option key={p} value={p}>{p.charAt(0).toUpperCase()+p.slice(1)}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Recipients (comma-separated emails)</label>
              <input className="input w-full" placeholder="alice@company.com, bob@company.com" value={recipients} onChange={e => setRecipients(e.target.value)} />
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
              Enabled
            </label>
            <div className="flex gap-2">
              <button className="btn-primary" onClick={handleCreate} disabled={saving}>{saving ? 'Saving…' : 'Create Report'}</button>
              <button className="btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
            </div>
          </div>
        )}

        {reports.length === 0 ? (
          <div className="card text-center py-10 text-gray-400 text-sm">No scheduled reports yet.</div>
        ) : (
          <div className="space-y-3">
            {reports.map(r => (
              <div key={r.id} className="card">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-800">{r.name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${PERIOD_COLORS[r.period]}`}>
                        {r.period}
                      </span>
                      {!r.enabled && <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded">Paused</span>}
                    </div>
                    <p className="text-sm text-gray-600">Metric: <strong>{METRIC_LABELS[r.metric] ?? r.metric}</strong></p>
                    <p className="text-xs text-gray-400">To: {r.recipients.join(', ')}</p>
                    {r.last_run_at && <p className="text-xs text-gray-400">Last run: {new Date(r.last_run_at).toLocaleString()}</p>}
                  </div>
                  <div className="flex gap-2 items-center flex-shrink-0">
                    <button className="text-xs text-blue-600 hover:text-blue-800 font-medium" onClick={() => handleRun(r)}>Run now</button>
                    <button className="text-xs text-gray-500 hover:text-gray-700" onClick={() => toggleEnabled(r)}>
                      {r.enabled ? 'Pause' : 'Enable'}
                    </button>
                    <button className="text-xs text-red-500 hover:text-red-700" onClick={() => handleDelete(r)}>Delete</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

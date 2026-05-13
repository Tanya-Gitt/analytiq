'use client';

import { useState } from 'react';
import useSWR from 'swr';
import {
  GdprOptOut,
  GdprExport,
  listOptOuts,
  gdprExport,
  gdprOptOut,
  gdprRemoveOptOut,
  gdprForget,
} from '@/lib/api';

export default function GdprPage() {
  const { data: optOuts = [], mutate: reloadOptOuts } = useSWR<GdprOptOut[]>('gdpr/opt-outs', listOptOuts);

  const [lookupId,  setLookupId]  = useState('');
  const [exportData, setExportData] = useState<GdprExport | null>(null);
  const [optOutId,  setOptOutId]  = useState('');
  const [forgetId,  setForgetId]  = useState('');
  const [msg,       setMsg]       = useState<{ text: string; ok: boolean } | null>(null);
  const [loading,   setLoading]   = useState<string | null>(null);

  function flash(text: string, ok: boolean) {
    setMsg({ text, ok });
    setTimeout(() => setMsg(null), 4000);
  }

  async function handleExport() {
    if (!lookupId.trim()) return;
    setLoading('export');
    try {
      const data = await gdprExport(lookupId.trim());
      setExportData(data);
    } catch {
      flash('User not found or export failed', false);
    } finally {
      setLoading(null);
    }
  }

  async function handleOptOut() {
    if (!optOutId.trim()) return;
    setLoading('optout');
    try {
      await gdprOptOut(optOutId.trim());
      await reloadOptOuts();
      flash(`${optOutId.trim()} opted out`, true);
      setOptOutId('');
    } catch (e: unknown) {
      flash(e instanceof Error ? e.message : 'Error', false);
    } finally {
      setLoading(null);
    }
  }

  async function handleRemoveOptOut(userId: string) {
    try {
      await gdprRemoveOptOut(userId);
      await reloadOptOuts();
      flash(`Tracking re-enabled for ${userId}`, true);
    } catch {
      flash('Error removing opt-out', false);
    }
  }

  async function handleForget() {
    if (!forgetId.trim()) return;
    if (!confirm(`Permanently delete ALL data for "${forgetId.trim()}"? This cannot be undone.`)) return;
    setLoading('forget');
    try {
      const res = await gdprForget(forgetId.trim());
      flash(`Deleted ${res.events_deleted} events for ${forgetId.trim()}`, true);
      setForgetId('');
      setExportData(null);
    } catch {
      flash('Error erasing user data', false);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">GDPR / CCPA Compliance</h1>
        <p className="text-sm text-gray-500 mt-1">Data access, erasure, and opt-out management</p>
      </div>

      {msg && (
        <div className={`px-4 py-3 rounded-lg text-sm font-medium ${msg.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {msg.text}
        </div>
      )}

      {/* Right of Access */}
      <div className="card space-y-4">
        <h2 className="font-semibold text-gray-800">Right of Access — Data Export</h2>
        <p className="text-sm text-gray-500">Look up all data stored for a user ID.</p>
        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder="User ID or email"
            value={lookupId}
            onChange={e => setLookupId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleExport()}
          />
          <button className="btn-primary" onClick={handleExport} disabled={loading === 'export'}>
            {loading === 'export' ? 'Loading…' : 'Export'}
          </button>
        </div>

        {exportData && (
          <div className="mt-4 space-y-3">
            <div className="flex items-center gap-4 text-sm">
              <span className="font-medium">{exportData.user_id}</span>
              <span className={`badge ${exportData.opted_out ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                {exportData.opted_out ? 'Opted out' : 'Tracking active'}
              </span>
              <span className="text-gray-500">{exportData.total_events} events</span>
            </div>
            <div className="max-h-56 overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-100">
              {exportData.events.slice(0, 50).map((ev, i) => (
                <div key={i} className="px-4 py-2 text-xs flex justify-between">
                  <span className="font-mono font-medium">{ev.event_name}</span>
                  <span className="text-gray-400">{new Date(ev.received_at).toLocaleString()}</span>
                </div>
              ))}
              {exportData.total_events > 50 && (
                <div className="px-4 py-2 text-xs text-gray-400 text-center">
                  +{exportData.total_events - 50} more events
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <button
                className="text-xs text-gray-500 hover:text-gray-700 underline"
                onClick={() => {
                  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
                  const a = document.createElement('a');
                  a.href = URL.createObjectURL(blob);
                  a.download = `gdpr-export-${exportData.user_id}.json`;
                  a.click();
                }}
              >
                Download JSON
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Right to be Forgotten */}
      <div className="card space-y-4 border-red-100">
        <h2 className="font-semibold text-gray-800">Right to Erasure — Forget User</h2>
        <p className="text-sm text-gray-500">Permanently delete all events for a user. This action cannot be undone.</p>
        <div className="flex gap-2">
          <input
            className="input flex-1 border-red-200 focus:ring-red-400"
            placeholder="User ID"
            value={forgetId}
            onChange={e => setForgetId(e.target.value)}
          />
          <button
            className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-50 transition-colors"
            onClick={handleForget}
            disabled={loading === 'forget' || !forgetId.trim()}
          >
            {loading === 'forget' ? 'Deleting…' : 'Erase Data'}
          </button>
        </div>
      </div>

      {/* Opt-out management */}
      <div className="card space-y-4">
        <h2 className="font-semibold text-gray-800">Tracking Opt-Outs</h2>
        <p className="text-sm text-gray-500">Events from opted-out users are silently dropped at ingest.</p>

        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder="User ID to opt out"
            value={optOutId}
            onChange={e => setOptOutId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleOptOut()}
          />
          <button className="btn-primary" onClick={handleOptOut} disabled={loading === 'optout'}>
            {loading === 'optout' ? 'Saving…' : 'Add Opt-Out'}
          </button>
        </div>

        {optOuts.length === 0 ? (
          <p className="text-sm text-gray-400 py-2">No opted-out users.</p>
        ) : (
          <div className="border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-72 overflow-y-auto">
            {optOuts.map(row => (
              <div key={row.user_id} className="px-4 py-3 flex items-center justify-between text-sm">
                <div>
                  <span className="font-medium font-mono">{row.user_id}</span>
                  <span className="ml-3 text-gray-400 text-xs">{new Date(row.opted_out_at).toLocaleString()}</span>
                </div>
                <button
                  className="text-xs text-blue-600 hover:text-blue-800"
                  onClick={() => handleRemoveOptOut(row.user_id)}
                >
                  Re-enable
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

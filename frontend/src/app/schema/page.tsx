'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { authHeader } from '@/lib/auth';
import ConfirmDialog from '@/components/ConfirmDialog';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';
const req = (url: string) => fetch(`${BASE}${url}`, { headers: authHeader() }).then(r => r.json());

interface Schema {
  id:          string;
  event_name:  string;
  properties:  Record<string, { type: string; required: boolean; description: string }>;
  strict_mode: boolean;
  updated_at:  string;
}
interface Violation  { event_name: string; violation: string; sample_props: Record<string,unknown>; occurred_at: string }
interface PiiSummary { event_name: string; redaction_events: number; fields_redacted: number; last_seen: string | null }

type Tab = 'schemas' | 'pii';

export default function SchemaPage() {
  const [tab, setTab] = useState<Tab>('schemas');

  const { data: schemas = [], mutate: reloadSchemas } = useSWR<Schema[]>('/schema', req);
  const { data: violations = [] }                     = useSWR<Violation[]>('/schema/violations', req);
  const { data: piiData = [] }                        = useSWR<PiiSummary[]>('/schema/pii-summary', req);

  const [showAdd,      setShowAdd]      = useState(false);
  const [newEvent,     setNewEvent]     = useState('');
  const [strictMode,   setStrictMode]   = useState(false);
  const [fields,       setFields]       = useState<{name:string;type:string;required:boolean}[]>([{name:'',type:'string',required:false}]);
  const [inferred,     setInferred]     = useState<Record<string,{type:string;required:boolean;description:string}> | null>(null);
  const [inferName,    setInferName]    = useState('');
  const [saving,       setSaving]       = useState(false);
  const [msg,          setMsg]          = useState<{text:string;ok:boolean}|null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  function flash(text: string, ok: boolean) {
    setMsg({text, ok});
    setTimeout(() => setMsg(null), 4000);
  }

  async function handleSave() {
    if (!newEvent.trim()) return;
    setSaving(true);
    try {
      const properties: Record<string, unknown> = {};
      fields.filter(f => f.name.trim()).forEach(f => {
        properties[f.name.trim()] = {type: f.type, required: f.required, description: ''};
      });
      const res = await fetch(`${BASE}/schema`, {
        method: 'POST',
        headers: {'Content-Type':'application/json',...authHeader()},
        body: JSON.stringify({event_name: newEvent.trim(), properties, strict_mode: strictMode}),
      });
      if (!res.ok) throw new Error(await res.text());
      await reloadSchemas();
      setShowAdd(false);
      setNewEvent(''); setFields([{name:'',type:'string',required:false}]); setStrictMode(false);
      flash('Schema saved', true);
    } catch(e) { flash(e instanceof Error ? e.message : 'Error', false); }
    finally { setSaving(false); }
  }

  async function doDelete(eventName: string) {
    await fetch(`${BASE}/schema/${encodeURIComponent(eventName)}`, {method:'DELETE', headers: authHeader()});
    await reloadSchemas();
    flash('Schema deleted', true);
  }

  async function handleInfer(eventName: string) {
    setInferName(eventName);
    const data = await req(`/schema/infer/${encodeURIComponent(eventName)}`);
    setInferred(data.properties);
  }

  async function adoptInferred() {
    if (!inferred || !inferName) return;
    setSaving(true);
    try {
      await fetch(`${BASE}/schema`, {
        method: 'POST',
        headers: {'Content-Type':'application/json',...authHeader()},
        body: JSON.stringify({event_name: inferName, properties: inferred, strict_mode: false}),
      });
      await reloadSchemas();
      setInferred(null); setInferName('');
      flash('Schema adopted from data', true);
    } finally { setSaving(false); }
  }

  const totalPiiToday = piiData.reduce((s, r) => s + r.redaction_events, 0);
  const totalViolationsWeek = violations.length;

  return (
    <AppShell>
      <div className="p-6 max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Schema Registry</h1>
            <p className="text-sm text-gray-500 mt-1">Validate events and detect PII automatically</p>
          </div>
          {tab === 'schemas' && (
            <button className="btn-primary" onClick={() => setShowAdd(true)}>+ Add Schema</button>
          )}
        </div>

        {msg && (
          <div className={`px-4 py-3 rounded-lg text-sm font-medium ${msg.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {msg.text}
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 border-b border-gray-200">
          {(['schemas','pii'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px transition-colors ${tab===t ? 'border-brand-600 text-brand-700' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
            >
              {t === 'schemas' ? 'Schemas' : 'PII Monitor'}
            </button>
          ))}
        </div>

        {tab === 'schemas' && (
          <div className="space-y-4">
            {showAdd && (
              <div className="card space-y-4 border-brand-200">
                <h3 className="font-semibold text-gray-800">New Schema</h3>
                <input className="input w-full" placeholder="Event name" value={newEvent} onChange={e => setNewEvent(e.target.value)} />
                <div className="space-y-2">
                  {fields.map((f, i) => (
                    <div key={i} className="flex gap-2">
                      <input className="input flex-1" placeholder="Field name" value={f.name} onChange={e => setFields(ff => ff.map((x,j) => j===i ? {...x,name:e.target.value}:x))} />
                      <select className="input w-28" value={f.type} onChange={e => setFields(ff => ff.map((x,j) => j===i?{...x,type:e.target.value}:x))}>
                        {['string','number','boolean','object','array'].map(t => <option key={t}>{t}</option>)}
                      </select>
                      <label className="flex items-center gap-1 text-xs text-gray-600">
                        <input type="checkbox" checked={f.required} onChange={e => setFields(ff => ff.map((x,j) => j===i?{...x,required:e.target.checked}:x))} />
                        Required
                      </label>
                      <button className="text-red-400 hover:text-red-600 text-xs" onClick={() => setFields(ff => ff.filter((_,j) => j!==i))}>✕</button>
                    </div>
                  ))}
                  <button className="text-sm text-brand-600 hover:text-brand-700" onClick={() => setFields(ff => [...ff, {name:'',type:'string',required:false}])}>+ Add field</button>
                </div>
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input type="checkbox" checked={strictMode} onChange={e => setStrictMode(e.target.checked)} />
                  Strict mode (reject events with unknown fields)
                </label>
                <div className="flex gap-2">
                  <button className="btn-primary" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save Schema'}</button>
                  <button className="btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
                </div>
              </div>
            )}

            {inferred && (
              <div className="card border-blue-200 space-y-3">
                <h3 className="font-semibold text-gray-800">Inferred schema for <span className="font-mono">{inferName}</span></h3>
                <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden">
                  {Object.entries(inferred).map(([k, v]) => (
                    <div key={k} className="px-4 py-2 flex items-center gap-4 text-sm">
                      <span className="font-mono font-medium w-40 truncate">{k}</span>
                      <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">{v.type}</span>
                      {v.required && <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">required</span>}
                      <span className="text-gray-400 text-xs ml-auto">{v.description}</span>
                    </div>
                  ))}
                </div>
                <div className="flex gap-2">
                  <button className="btn-primary text-sm" onClick={adoptInferred} disabled={saving}>Adopt this schema</button>
                  <button className="btn-secondary text-sm" onClick={() => setInferred(null)}>Dismiss</button>
                </div>
              </div>
            )}

            {schemas.length === 0 ? (
              <div className="card text-center py-10 text-gray-400 text-sm">No schemas defined yet.</div>
            ) : (
              <div className="space-y-3">
                {schemas.map(s => (
                  <div key={s.id} className="card space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="font-mono font-semibold text-gray-800">{s.event_name}</span>
                        {s.strict_mode && <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded">strict</span>}
                        <span className="text-xs text-gray-400">{Object.keys(s.properties).length} fields · updated {new Date(s.updated_at).toLocaleDateString()}</span>
                      </div>
                      <div className="flex gap-2">
                        <button className="text-xs text-blue-600 hover:text-blue-800" onClick={() => handleInfer(s.event_name)}>Infer from data</button>
                        <button className="text-xs text-red-500 hover:text-red-700" onClick={() => setDeleteTarget(s.event_name)}>Delete</button>
                      </div>
                    </div>
                    {Object.keys(s.properties).length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(s.properties).map(([k, v]) => (
                          <span key={k} className={`text-xs px-2 py-0.5 rounded font-mono ${v.required ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}`}>
                            {k}: {v.type}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'pii' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="card text-center">
                <p className="text-2xl font-bold text-orange-600">{totalPiiToday}</p>
                <p className="text-sm text-gray-600">Events with PII redacted (30d)</p>
              </div>
              <div className="card text-center">
                <p className="text-2xl font-bold text-red-600">{totalViolationsWeek}</p>
                <p className="text-sm text-gray-600">Schema violations (7d)</p>
              </div>
            </div>

            {piiData.length > 0 && (
              <div className="card p-0 overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-200 text-sm font-medium text-gray-700">PII Redactions by Event (30d)</div>
                <table className="w-full text-sm">
                  <thead><tr className="bg-gray-50 border-b border-gray-200">
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Event</th>
                    <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Events</th>
                    <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Fields</th>
                    <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Last seen</th>
                  </tr></thead>
                  <tbody className="divide-y divide-gray-100">
                    {piiData.map(r => (
                      <tr key={r.event_name} className="hover:bg-gray-50">
                        <td className="px-4 py-2 font-mono text-xs">{r.event_name}</td>
                        <td className="px-4 py-2 text-right">{r.redaction_events}</td>
                        <td className="px-4 py-2 text-right">{r.fields_redacted}</td>
                        <td className="px-4 py-2 text-right text-gray-400 text-xs">{r.last_seen ? new Date(r.last_seen).toLocaleDateString() : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {violations.length > 0 && (
              <div className="card p-0 overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-200 text-sm font-medium text-gray-700">Recent Schema Violations (7d)</div>
                <div className="divide-y divide-gray-100 max-h-72 overflow-y-auto">
                  {violations.map((v, i) => (
                    <div key={i} className="px-4 py-3 text-sm">
                      <div className="flex justify-between">
                        <span className="font-mono font-medium">{v.event_name}</span>
                        <span className="text-xs text-gray-400">{new Date(v.occurred_at).toLocaleString()}</span>
                      </div>
                      <p className="text-xs text-red-600 mt-0.5">{v.violation}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title={`Delete schema for "${deleteTarget ?? ''}"?`}
        description="Ingest will no longer validate events with this name. Existing data is kept."
        confirmLabel="Delete schema"
        onConfirm={() => deleteTarget && doDelete(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
      />
    </AppShell>
  );
}

'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { getToken } from '@/lib/auth';
import ConfirmDialog from '@/components/ConfirmDialog';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';

interface EmbedToken {
  id: number;
  name: string;
  widget_type: string;
  config: Record<string, unknown>;
  expires_at: string | null;
  created_at: string;
  token_prefix: string;
}

const authFetch = (url: string) =>
  fetch(`${BASE}/${url}`, { headers: { Authorization: `Bearer ${getToken()}` } })
    .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); });

const WIDGET_TYPES = ['events_chart', 'top_events', 'funnel'];

export default function EmbedPage() {
  const { data: tokens = [], mutate } = useSWR<EmbedToken[]>('embed/tokens', authFetch);

  const [showCreate,   setShowCreate]   = useState(false);
  const [name,         setName]         = useState('');
  const [widgetType,   setWidgetType]   = useState('events_chart');
  const [expireDays,   setExpireDays]   = useState('');
  const [creating,     setCreating]     = useState(false);
  const [newToken,     setNewToken]     = useState<string | null>(null);
  const [copied,       setCopied]       = useState(false);
  const [msg,          setMsg]          = useState<{ text: string; ok: boolean } | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<EmbedToken | null>(null);

  function flash(text: string, ok: boolean) {
    setMsg({ text, ok });
    setTimeout(() => setMsg(null), 4000);
  }

  async function handleCreate() {
    if (!name.trim()) return;
    setCreating(true);
    try {
      const token = getToken();
      const body: Record<string, unknown> = { name: name.trim(), widget_type: widgetType };
      if (expireDays) body.expires_days = Number(expireDays);
      const res = await fetch(`${BASE}/embed/tokens`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setNewToken(data.token);
      setName(''); setExpireDays('');
      await mutate();
    } catch (e) {
      flash(e instanceof Error ? e.message : 'Create failed', false);
    } finally {
      setCreating(false);
    }
  }

  async function doRevoke(id: number) {
    const token = getToken();
    await fetch(`${BASE}/embed/tokens/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
    await mutate();
    flash('Token revoked', true);
  }

  function copySnippet(tokenStr: string) {
    const snippet = `<iframe src="${window.location.origin}/embed/widget/${tokenStr}" width="600" height="400" frameborder="0"></iframe>`;
    navigator.clipboard.writeText(snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <AppShell>
      <div className="p-6 max-w-4xl mx-auto space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Embedded Analytics</h1>
            <p className="text-sm text-gray-500 mt-1">Embed analytics widgets in external sites using signed tokens</p>
          </div>
          <button className="btn-primary" onClick={() => setShowCreate(v => !v)}>
            {showCreate ? 'Cancel' : '+ New Token'}
          </button>
        </div>

        {msg && (
          <div className={`px-4 py-3 rounded-lg text-sm font-medium ${msg.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {msg.text}
          </div>
        )}

        {/* Create form */}
        {showCreate && (
          <div className="card space-y-4">
            <h2 className="font-semibold text-gray-800">Create Embed Token</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
                <input className="input w-full" placeholder="e.g. Dashboard widget" value={name} onChange={e => setName(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Widget type</label>
                <select className="input w-full" value={widgetType} onChange={e => setWidgetType(e.target.value)}>
                  {WIDGET_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Expires (days, optional)</label>
                <input className="input w-full" type="number" placeholder="Never" value={expireDays} onChange={e => setExpireDays(e.target.value)} />
              </div>
            </div>
            <button className="btn-primary" onClick={handleCreate} disabled={creating || !name.trim()}>
              {creating ? 'Creating…' : 'Create Token'}
            </button>
          </div>
        )}

        {/* New token reveal */}
        {newToken && (
          <div className="card border-green-200 bg-green-50 space-y-3">
            <h2 className="font-semibold text-green-800">Token created — copy it now</h2>
            <p className="text-xs text-green-700">This token is shown once. Use it as the embed URL or in the iframe snippet below.</p>
            <div className="font-mono text-xs bg-white border border-green-200 rounded px-3 py-2 break-all">{newToken}</div>
            <div className="flex gap-2">
              <button className="btn-primary text-xs" onClick={() => { navigator.clipboard.writeText(newToken); }}>Copy token</button>
              <button className="text-xs px-3 py-1.5 border rounded-lg hover:bg-gray-50" onClick={() => copySnippet(newToken)}>
                {copied ? 'Copied!' : 'Copy iframe snippet'}
              </button>
              <button className="text-xs text-gray-400 hover:text-gray-600 underline ml-auto" onClick={() => setNewToken(null)}>Dismiss</button>
            </div>
            <p className="text-xs text-gray-500">Embed URL: <code className="bg-gray-100 px-1 rounded">{`/embed/widget/${newToken}`}</code></p>
          </div>
        )}

        {/* Token list */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-gray-800">Active Tokens</h2>
          {tokens.length === 0 ? (
            <p className="text-sm text-gray-400 py-2">No embed tokens yet. Create one above.</p>
          ) : (
            <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
              {tokens.map(t => (
                <div key={t.id} className="px-4 py-3 flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm text-gray-800">{t.name}</span>
                      <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">{t.widget_type}</span>
                    </div>
                    <div className="text-xs text-gray-400 font-mono">{t.token_prefix}</div>
                    <div className="text-xs text-gray-400">
                      Created {new Date(t.created_at).toLocaleDateString()}
                      {t.expires_at && ` · Expires ${new Date(t.expires_at).toLocaleDateString()}`}
                    </div>
                  </div>
                  <button
                    className="text-xs text-red-600 hover:text-red-800"
                    onClick={() => setRevokeTarget(t)}
                  >
                    Revoke
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* How to embed */}
        <div className="card space-y-3 bg-gray-50">
          <h2 className="font-semibold text-gray-800">How to embed</h2>
          <ol className="text-sm text-gray-600 space-y-2 list-decimal list-inside">
            <li>Create a token above and copy the embed URL</li>
            <li>Add an iframe to your external site:</li>
          </ol>
          <pre className="bg-white border rounded-lg text-xs p-3 overflow-x-auto text-gray-700">{`<iframe
  src="https://your-domain.com/embed/widget/<TOKEN>"
  width="600"
  height="400"
  frameborder="0"
></iframe>`}</pre>
          <p className="text-xs text-gray-400">The widget page renders without authentication — the token itself controls access.</p>
        </div>
      </div>

      <ConfirmDialog
        open={!!revokeTarget}
        title={`Revoke token "${revokeTarget?.name ?? ''}"?`}
        description="Any iframes or external sites using this token will immediately stop loading the widget."
        confirmLabel="Revoke token"
        onConfirm={() => revokeTarget && doRevoke(revokeTarget.id)}
        onClose={() => setRevokeTarget(null)}
      />
    </AppShell>
  );
}

'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { authHeader } from '@/lib/auth';
import ConfirmDialog from '@/components/ConfirmDialog';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';
const req = (url: string) => fetch(`${BASE}${url}`, { headers: authHeader() }).then(r => r.json());

interface ApiKey {
  id:           string;
  name:         string;
  prefix:       string;
  scopes:       string[];
  revoked:      boolean;
  created_at:   string;
  last_used_at: string | null;
  expires_at:   string | null;
  key?:         string;  // only on creation
}

const SCOPE_COLORS: Record<string, string> = {
  ingest: 'bg-green-100 text-green-700',
  read:   'bg-blue-100 text-blue-700',
  admin:  'bg-red-100 text-red-700',
};

export default function ApiKeysPage() {
  const { data: keys = [], mutate } = useSWR<ApiKey[]>('/api-keys', req);

  const [showCreate,   setShowCreate]   = useState(false);
  const [name,         setName]         = useState('');
  const [scopes,       setScopes]       = useState<string[]>(['read']);
  const [expireDays,   setExpireDays]   = useState('');
  const [creating,     setCreating]     = useState(false);
  const [newKey,       setNewKey]       = useState<string | null>(null);
  const [copied,       setCopied]       = useState(false);
  const [msg,          setMsg]          = useState<{text:string;ok:boolean}|null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);

  function flash(text: string, ok: boolean) {
    setMsg({text, ok});
    setTimeout(() => setMsg(null), 4000);
  }

  function toggleScope(s: string) {
    setScopes(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);
  }

  async function handleCreate() {
    if (!name.trim() || scopes.length === 0) return;
    setCreating(true);
    try {
      const res = await fetch(`${BASE}/api-keys`, {
        method: 'POST',
        headers: {'Content-Type':'application/json', ...authHeader()},
        body: JSON.stringify({
          name: name.trim(),
          scopes,
          expires_days: expireDays ? parseInt(expireDays) : null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const created: ApiKey = await res.json();
      setNewKey(created.key ?? null);
      await mutate();
      setShowCreate(false);
      setName(''); setScopes(['read']); setExpireDays('');
    } catch (e) {
      flash(e instanceof Error ? e.message : 'Error creating key', false);
    } finally {
      setCreating(false);
    }
  }

  async function doRevoke(id: string, keyName: string) {
    await fetch(`${BASE}/api-keys/${id}`, { method: 'DELETE', headers: authHeader() });
    await mutate();
    flash(`Key "${keyName}" revoked`, true);
  }

  async function copyKey() {
    if (!newKey) return;
    await navigator.clipboard.writeText(newKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <AppShell>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">API Keys</h1>
            <p className="text-sm text-gray-500 mt-1">Scoped keys for programmatic access</p>
          </div>
          <button className="btn-primary" onClick={() => setShowCreate(true)}>+ Create Key</button>
        </div>

        {msg && (
          <div className={`px-4 py-3 rounded-lg text-sm font-medium ${msg.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {msg.text}
          </div>
        )}

        {/* One-time key reveal */}
        {newKey && (
          <div className="card border-green-200 bg-green-50 space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-green-700 font-semibold">🎉 Key created — copy it now</span>
              <span className="text-xs text-green-600">You won't be able to see this key again.</span>
            </div>
            <div className="flex gap-2">
              <code className="flex-1 bg-white border border-green-200 rounded-lg px-3 py-2 text-sm font-mono text-gray-800 overflow-auto">
                {newKey}
              </code>
              <button
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${copied ? 'bg-green-600 text-white' : 'bg-white border border-green-300 text-green-700 hover:bg-green-100'}`}
                onClick={copyKey}
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <button className="text-xs text-green-600 underline" onClick={() => setNewKey(null)}>Dismiss</button>
          </div>
        )}

        {/* Create form */}
        {showCreate && (
          <div className="card space-y-4 border-brand-200">
            <h3 className="font-semibold text-gray-800">New API Key</h3>
            <input className="input w-full" placeholder="Key name (e.g. Production Ingest)" value={name} onChange={e => setName(e.target.value)} />
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-2">Scopes</label>
              <div className="flex gap-3">
                {['ingest','read','admin'].map(s => (
                  <label key={s} className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={scopes.includes(s)} onChange={() => toggleScope(s)} />
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${SCOPE_COLORS[s]}`}>{s}</span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-gray-400 mt-1">ingest = write events · read = query data · admin = full access</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Expiry (optional)</label>
              <select className="input" value={expireDays} onChange={e => setExpireDays(e.target.value)}>
                <option value="">Never expires</option>
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="365">1 year</option>
              </select>
            </div>
            <div className="flex gap-2">
              <button className="btn-primary" onClick={handleCreate} disabled={creating || !name.trim() || scopes.length === 0}>
                {creating ? 'Creating…' : 'Create Key'}
              </button>
              <button className="btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
            </div>
          </div>
        )}

        {/* Keys table */}
        {keys.length === 0 ? (
          <div className="card text-center py-10 text-gray-400 text-sm">No API keys yet.</div>
        ) : (
          <div className="card p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Key</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Scopes</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last used</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Expires</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {keys.map(k => (
                  <tr key={k.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">{k.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">{k.prefix}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        {k.scopes.map(s => (
                          <span key={s} className={`text-xs px-2 py-0.5 rounded font-medium ${SCOPE_COLORS[s] ?? 'bg-gray-100 text-gray-600'}`}>{s}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">{k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : 'Never'}</td>
                    <td className="px-4 py-3 text-xs text-gray-400">{k.expires_at ? new Date(k.expires_at).toLocaleDateString() : '—'}</td>
                    <td className="px-4 py-3 text-right">
                      <button className="text-xs text-red-500 hover:text-red-700" onClick={() => setRevokeTarget(k)}>Revoke</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!revokeTarget}
        title={`Revoke key "${revokeTarget?.name ?? ''}"?`}
        description="Any services using this key will lose access immediately. You'll need to create a new key and update your integrations."
        confirmLabel="Revoke key"
        onConfirm={() => revokeTarget && doRevoke(revokeTarget.id, revokeTarget.name)}
        onClose={() => setRevokeTarget(null)}
      />
    </AppShell>
  );
}

'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { getToken } from '@/lib/auth';

interface SSOConfig {
  provider: string;
  client_id: string;
  discovery_url: string;
  enabled: boolean;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api';

const authFetch = (url: string) =>
  fetch(`${BASE}/${url}`, { headers: { Authorization: `Bearer ${getToken()}` } })
    .then(r => r.json());

const PROVIDERS = [
  { id: 'google', name: 'Google', color: 'bg-red-100 text-red-700' },
  { id: 'github', name: 'GitHub', color: 'bg-gray-100 text-gray-700' },
  { id: 'okta',   name: 'Okta',   color: 'bg-blue-100 text-blue-700' },
  { id: 'azure',  name: 'Azure AD', color: 'bg-blue-100 text-blue-800' },
  { id: 'oidc',   name: 'Custom OIDC', color: 'bg-purple-100 text-purple-700' },
];

export default function SSOSettingsPage() {
  const { data: config } = useSWR<SSOConfig>('auth/sso/config', authFetch);

  const [provider,      setProvider]      = useState('okta');
  const [clientId,      setClientId]      = useState('');
  const [clientSecret,  setClientSecret]  = useState('');
  const [discoveryUrl,  setDiscoveryUrl]  = useState('');
  const [saving,        setSaving]        = useState(false);
  const [msg,           setMsg]           = useState<{ text: string; ok: boolean } | null>(null);

  function flash(text: string, ok: boolean) {
    setMsg({ text, ok });
    setTimeout(() => setMsg(null), 4000);
  }

  function getDiscoveryPlaceholder() {
    if (provider === 'okta')  return 'https://your-org.okta.com/.well-known/openid-configuration';
    if (provider === 'azure') return 'https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration';
    return 'https://your-idp.com/.well-known/openid-configuration';
  }

  async function handleSave() {
    if (!clientId.trim() || !discoveryUrl.trim()) {
      flash('Client ID and Discovery URL are required', false);
      return;
    }
    setSaving(true);
    try {
      const token = getToken();
      const res = await fetch(`${BASE}/auth/sso/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          provider,
          client_id:     clientId,
          client_secret: clientSecret,
          discovery_url: discoveryUrl,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      flash('SSO configuration saved', true);
    } catch (e) {
      flash(e instanceof Error ? e.message : 'Save failed', false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className="p-6 max-w-3xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">SSO / SAML / OAuth</h1>
          <p className="text-sm text-gray-500 mt-1">Configure single sign-on for your organization</p>
        </div>

        {msg && (
          <div className={`px-4 py-3 rounded-lg text-sm font-medium ${msg.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {msg.text}
          </div>
        )}

        {/* Quick-start providers */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-gray-800">Built-in Providers</h2>
          <p className="text-sm text-gray-500">Google and GitHub work out-of-the-box — no per-org configuration needed.</p>
          <div className="grid grid-cols-2 gap-3">
            {['google', 'github'].map(p => {
              const prov = PROVIDERS.find(x => x.id === p)!;
              return (
                <div key={p} className="flex items-center gap-3 p-3 border rounded-lg">
                  <span className={`text-xs px-2 py-1 rounded font-medium ${prov.color}`}>{prov.name}</span>
                  <div>
                    <p className="text-xs font-medium text-gray-700">Ready to use</p>
                    <p className="text-xs text-gray-400">Login at /api/auth/sso/{p}/start</p>
                  </div>
                  <a
                    href={`/api/auth/sso/${p}/start`}
                    className="ml-auto text-xs text-blue-600 hover:text-blue-800"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Test →
                  </a>
                </div>
              );
            })}
          </div>
        </div>

        {/* Per-org OIDC config */}
        <div className="card space-y-4">
          <h2 className="font-semibold text-gray-800">Custom OIDC / Okta / Azure AD</h2>
          <p className="text-sm text-gray-500">Configure a per-org OIDC provider. Requires client credentials from your IdP.</p>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Provider</label>
            <div className="flex gap-2 flex-wrap">
              {PROVIDERS.filter(p => !['google', 'github'].includes(p.id)).map(p => (
                <button
                  key={p.id}
                  className={`text-xs px-3 py-1.5 rounded-full border font-medium transition-colors ${provider === p.id ? p.color + ' border-current' : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}
                  onClick={() => setProvider(p.id)}
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Client ID</label>
              <input
                className="input w-full"
                placeholder="0oa5abc123..."
                value={clientId}
                onChange={e => setClientId(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Client Secret</label>
              <input
                className="input w-full"
                type="password"
                placeholder="••••••••"
                value={clientSecret}
                onChange={e => setClientSecret(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">OIDC Discovery URL</label>
            <input
              className="input w-full"
              placeholder={getDiscoveryPlaceholder()}
              value={discoveryUrl}
              onChange={e => setDiscoveryUrl(e.target.value)}
            />
            <p className="text-xs text-gray-400 mt-1">
              The <code className="bg-gray-100 px-1 rounded">.well-known/openid-configuration</code> endpoint for your IdP
            </p>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-700 space-y-1">
            <p className="font-medium">Callback URL to register with your IdP:</p>
            <code className="block bg-white border border-blue-100 rounded px-2 py-1">
              {typeof window !== 'undefined' ? window.location.origin : 'https://your-domain.com'}/api/auth/sso/callback
            </code>
          </div>

          <div className="flex gap-2">
            <button className="btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save Configuration'}
            </button>
            {provider !== 'oidc' && (
              <a
                href={`/api/auth/sso/${provider}/start`}
                className="text-xs px-3 py-2 border rounded-lg hover:bg-gray-50 text-gray-600 flex items-center"
                target="_blank"
                rel="noreferrer"
              >
                Test Login →
              </a>
            )}
          </div>
        </div>

        {/* Current config */}
        {config && (
          <div className="card space-y-2 bg-gray-50">
            <h3 className="text-sm font-semibold text-gray-700">Current configuration</h3>
            <div className="text-xs space-y-1 text-gray-600">
              <div className="flex gap-2"><span className="text-gray-400 w-24">Provider</span><span>{config.provider}</span></div>
              <div className="flex gap-2"><span className="text-gray-400 w-24">Client ID</span><span className="font-mono">{config.client_id}</span></div>
              <div className="flex gap-2"><span className="text-gray-400 w-24">Status</span><span className={config.enabled ? 'text-green-600' : 'text-gray-400'}>{config.enabled ? 'Active' : 'Disabled'}</span></div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

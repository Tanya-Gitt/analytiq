'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import {
  getMe, rotateApiKey, getTeam, inviteMember, removeMember,
  updateMemberRole, cancelInvite, listSSOConfigs, createSSOConfig, deleteSSOConfig,
  ApiError, type TeamMember, type PendingInvite, type SSOConfig,
} from '@/lib/api';

// ── Copy helper ───────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function handleCopy() {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const el = document.createElement('textarea');
      el.value = text; document.body.appendChild(el); el.select();
      document.execCommand('copy'); document.body.removeChild(el);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <button onClick={handleCopy} className="text-xs font-medium text-brand-600 hover:underline ml-2">
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

// ── Team panel ────────────────────────────────────────────────────────────────

function TeamPanel({ currentUserId }: { currentUserId: string }) {
  const { data, mutate } = useSWR('team', getTeam);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole,  setInviteRole]  = useState<'admin' | 'viewer'>('viewer');
  const [inviting,    setInviting]    = useState(false);
  const [inviteErr,   setInviteErr]   = useState('');
  const [inviteOk,    setInviteOk]    = useState('');

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true); setInviteErr(''); setInviteOk('');
    try {
      const res = await inviteMember(inviteEmail, inviteRole);
      setInviteOk(`Invite sent to ${res.email}. Share link: ${window.location.origin}${res.invite_url}`);
      setInviteEmail('');
      await mutate();
    } catch (e: unknown) { setInviteErr((e as ApiError).message); }
    finally { setInviting(false); }
  }

  async function handleRemove(m: TeamMember) {
    if (!confirm(`Remove ${m.email} from the org?`)) return;
    await removeMember(m.id);
    await mutate();
  }

  async function handleRoleChange(m: TeamMember, role: 'admin' | 'viewer') {
    await updateMemberRole(m.id, role);
    await mutate();
  }

  async function handleCancelInvite(inv: PendingInvite) {
    await cancelInvite(inv.id);
    await mutate();
  }

  return (
    <div className="card space-y-5">
      <h2 className="text-sm font-semibold text-gray-900">Team members</h2>

      {/* Current members */}
      <div className="space-y-2">
        {data?.members.map(m => (
          <div key={m.id} className="flex items-center gap-3 py-2">
            <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
              <span className="text-xs font-semibold text-indigo-700">
                {m.email[0].toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-900 truncate">{m.email}</p>
            </div>
            {m.id === currentUserId ? (
              <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-medium">
                {m.role} · you
              </span>
            ) : (
              <select
                value={m.role}
                onChange={e => handleRoleChange(m, e.target.value as 'admin' | 'viewer')}
                className="text-xs border border-gray-200 rounded-lg px-2 py-1
                           focus:outline-none focus:ring-2 focus:ring-indigo-400"
              >
                <option value="admin">admin</option>
                <option value="viewer">viewer</option>
              </select>
            )}
            {m.id !== currentUserId && (
              <button
                onClick={() => handleRemove(m)}
                className="text-xs text-red-400 hover:text-red-600 px-2"
                title="Remove member"
              >
                Remove
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Pending invites */}
      {data?.pending_invites.length ? (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
            Pending invites
          </p>
          <div className="space-y-1.5">
            {data.pending_invites.map(inv => (
              <div key={inv.id} className="flex items-center gap-2 bg-amber-50 rounded-lg px-3 py-2">
                <p className="text-xs text-gray-700 flex-1 truncate">{inv.email}</p>
                <span className="text-xs text-amber-600">{inv.role}</span>
                <span className="text-xs text-gray-400">
                  expires {inv.expires_at.slice(0, 10)}
                </span>
                <button
                  onClick={() => handleCancelInvite(inv)}
                  className="text-xs text-red-400 hover:text-red-600"
                >
                  Cancel
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Invite form */}
      <div className="pt-4 border-t border-gray-100">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">
          Invite someone
        </p>
        <form onSubmit={handleInvite} className="flex gap-2">
          <input
            type="email"
            value={inviteEmail}
            onChange={e => setInviteEmail(e.target.value)}
            placeholder="colleague@company.com"
            required
            className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2
                       focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
          <select
            value={inviteRole}
            onChange={e => setInviteRole(e.target.value as 'admin' | 'viewer')}
            className="text-sm border border-gray-200 rounded-lg px-2 py-2
                       focus:outline-none focus:ring-2 focus:ring-indigo-400"
          >
            <option value="viewer">viewer</option>
            <option value="admin">admin</option>
          </select>
          <button
            type="submit" disabled={inviting}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60
                       text-white text-sm font-medium px-4 rounded-lg transition-colors"
          >
            {inviting ? '…' : 'Invite'}
          </button>
        </form>
        {inviteOk && (
          <p className="text-xs text-green-700 bg-green-50 rounded-lg px-3 py-2 mt-2 break-all">
            ✓ {inviteOk}
          </p>
        )}
        {inviteErr && (
          <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 mt-2">{inviteErr}</p>
        )}
      </div>
    </div>
  );
}

// ── SSO panel ─────────────────────────────────────────────────────────────────

function SSOPanel() {
  const { data: configs, mutate } = useSWR('sso-configs', listSSOConfigs);
  const [provider,      setProvider]      = useState<'google' | 'github' | 'oidc'>('oidc');
  const [clientId,      setClientId]      = useState('');
  const [clientSecret,  setClientSecret]  = useState('');
  const [discoveryUrl,  setDiscoveryUrl]  = useState('');
  const [saving,        setSaving]        = useState(false);
  const [saveErr,       setSaveErr]       = useState('');
  const [saveOk,        setSaveOk]        = useState('');

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setSaveErr(''); setSaveOk('');
    try {
      await createSSOConfig({ provider, client_id: clientId, client_secret: clientSecret, discovery_url: discoveryUrl || undefined });
      setSaveOk('SSO configuration saved.');
      setClientId(''); setClientSecret(''); setDiscoveryUrl('');
      await mutate();
    } catch (err) {
      setSaveErr(err instanceof ApiError ? err.message : 'Save failed');
    } finally { setSaving(false); }
  }

  async function handleDelete(p: string) {
    if (!confirm(`Remove ${p} SSO config?`)) return;
    try { await deleteSSOConfig(p); await mutate(); }
    catch (err) { alert(err instanceof ApiError ? err.message : 'Delete failed'); }
  }

  const PROVIDER_HINTS: Record<string, { discovery: string; docs: string }> = {
    google: { discovery: 'https://accounts.google.com', docs: 'https://console.cloud.google.com/' },
    github: { discovery: '', docs: 'https://github.com/settings/applications/new' },
    oidc:   { discovery: 'https://your-okta-domain.okta.com', docs: 'https://developer.okta.com/' },
  };

  return (
    <div className="card space-y-5">
      <div>
        <h2 className="text-sm font-semibold text-gray-900">Single Sign-On (SSO)</h2>
        <p className="text-xs text-gray-500 mt-1">
          Allow your team to sign in with Google, GitHub, Okta, Azure AD, or any OIDC-compatible provider.
          Members who sign in via SSO are provisioned automatically.
        </p>
      </div>

      {/* Existing configs */}
      {configs && configs.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Active providers</p>
          {configs.map((c: SSOConfig) => (
            <div key={c.id} className="flex items-center gap-3 bg-gray-50 rounded-xl px-4 py-3">
              <span className={`w-2 h-2 rounded-full ${c.enabled ? 'bg-emerald-500' : 'bg-gray-300'}`} />
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-800">{c.provider}</p>
                {c.discovery_url && (
                  <p className="text-xs text-gray-400 truncate">{c.discovery_url}</p>
                )}
              </div>
              <span className="text-xs text-gray-400">Client: {c.client_id.slice(0, 12)}…</span>
              <button
                onClick={() => handleDelete(c.provider)}
                className="text-xs text-red-400 hover:text-red-600"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add / update config */}
      <form onSubmit={handleSave} className="space-y-3 pt-3 border-t border-gray-100">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Add / update provider</p>

        <div className="flex gap-2">
          {(['google', 'github', 'oidc'] as const).map(p => (
            <button
              key={p}
              type="button"
              onClick={() => setProvider(p)}
              className={`flex-1 rounded-xl py-2 text-xs font-medium border transition-colors ${
                provider === p
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
              }`}
            >
              {p === 'oidc' ? 'Custom OIDC' : p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>

        <p className="text-xs text-gray-400">
          {provider === 'google' && <>Create OAuth credentials at <a href={PROVIDER_HINTS.google.docs} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">Google Cloud Console</a>. Discovery URL is set automatically.</>}
          {provider === 'github' && <>Register an OAuth app at <a href={PROVIDER_HINTS.github.docs} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">GitHub Developer Settings</a>. Callback URL: <code className="bg-gray-100 rounded px-1">/api/auth/sso/callback</code></>}
          {provider === 'oidc' && <>Supports Okta, Azure AD, Keycloak, Auth0, Ping and any OIDC-compliant provider. Paste the base URL (without /.well-known/openid-configuration).</>}
        </p>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Client ID</label>
            <input className="input text-sm" placeholder="client_id" value={clientId}
              onChange={e => setClientId(e.target.value)} required />
          </div>
          <div>
            <label className="label">Client Secret</label>
            <input className="input text-sm" type="password" placeholder="client_secret" value={clientSecret}
              onChange={e => setClientSecret(e.target.value)} required />
          </div>
        </div>

        {provider !== 'github' && (
          <div>
            <label className="label">
              Discovery URL
              {provider === 'google' && <span className="text-gray-400 normal-case font-normal ml-1">(auto-filled for Google)</span>}
            </label>
            <input className="input text-sm" placeholder={PROVIDER_HINTS[provider]?.discovery || 'https://…'}
              value={provider === 'google' ? 'https://accounts.google.com' : discoveryUrl}
              readOnly={provider === 'google'}
              onChange={e => setDiscoveryUrl(e.target.value)}
            />
          </div>
        )}

        <button type="submit" disabled={saving}
          className="btn-primary text-sm w-full disabled:opacity-60">
          {saving ? 'Saving…' : 'Save SSO configuration'}
        </button>

        {saveOk  && <p className="text-xs text-green-700 bg-green-50 rounded-lg px-3 py-2">✓ {saveOk}</p>}
        {saveErr && <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{saveErr}</p>}
      </form>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { data, error, isLoading, mutate } = useSWR('me', getMe);

  const [showKey,       setShowKey]       = useState(false);
  const [rotating,      setRotating]      = useState(false);
  const [rotateError,   setRotateError]   = useState('');
  const [rotateSuccess, setRotateSuccess] = useState(false);

  async function handleRotate() {
    if (!confirm(
      'Rotate your API key? The current key will stop working immediately. ' +
      'You must update any JS SDK integrations or webhook senders with the new key.',
    )) return;
    setRotating(true); setRotateError(''); setRotateSuccess(false);
    try {
      const result = await rotateApiKey();
      await mutate(prev => prev ? { ...prev, api_key: result.api_key } : prev, false);
      setShowKey(true); setRotateSuccess(true);
    } catch (err) {
      setRotateError(err instanceof ApiError ? err.message : 'Rotation failed');
    } finally { setRotating(false); }
  }

  return (
    <AppShell>
      <div className="max-w-2xl">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-gray-900">Settings</h1>
          <p className="text-sm text-gray-500 mt-0.5">Manage your workspace and API credentials</p>
        </div>

        {isLoading && (
          <div className="space-y-4 animate-pulse">
            <div className="card h-24 bg-gray-100" />
            <div className="card h-32 bg-gray-100" />
          </div>
        )}
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error.message}
          </div>
        )}

        {data && (
          <div className="space-y-6">
            {/* Workspace */}
            <div className="card space-y-3">
              <h2 className="text-sm font-semibold text-gray-900">Workspace</h2>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Org name</p>
                  <p className="text-gray-900 font-medium">{data.org_name}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Your email</p>
                  <p className="text-gray-900">{data.email}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Your role</p>
                  <span className={`inline-flex text-xs font-medium px-2 py-0.5 rounded-full ${
                    (data as any).role === 'admin'
                      ? 'bg-indigo-100 text-indigo-700'
                      : 'bg-gray-100 text-gray-600'
                  }`}>
                    {(data as any).role ?? 'admin'}
                  </span>
                </div>
              </div>
            </div>

            {/* Team members */}
            <TeamPanel currentUserId={data.user_id} />

            {/* SSO */}
            <SSOPanel />

            {/* API key */}
            <div className="card space-y-4">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">API Key</h2>
                <p className="text-xs text-gray-500 mt-1">
                  Used to authenticate the JavaScript SDK and direct API calls.
                  Keep this secret — it grants write access to your analytics data.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <code className="flex-1 text-xs font-mono bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-gray-700 overflow-hidden text-ellipsis whitespace-nowrap">
                  {showKey ? data.api_key : '••••••••••••••••••••••••••••••••••••••••••••••••'}
                </code>
                <button
                  onClick={() => setShowKey(v => !v)}
                  className="text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-2 whitespace-nowrap"
                >
                  {showKey ? 'Hide' : 'Show'}
                </button>
                {showKey && <CopyButton text={data.api_key} />}
              </div>
              {showKey && (
                <div className="rounded-lg bg-gray-900 px-4 py-3 text-xs font-mono text-gray-100 overflow-x-auto">
                  <p className="text-gray-400 mb-1">{'// JavaScript SDK'}</p>
                  <p>{`Analytics.init('${data.api_key}', { host: window.location.origin });`}</p>
                </div>
              )}
              <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                <div>
                  <p className="text-xs font-medium text-gray-700">Rotate API key</p>
                  <p className="text-xs text-gray-400 mt-0.5">Generates a new key. The old key stops working immediately.</p>
                </div>
                <button
                  onClick={handleRotate} disabled={rotating}
                  className="btn-secondary text-xs text-red-600 border-red-200 hover:bg-red-50 disabled:opacity-50"
                >
                  {rotating ? 'Rotating…' : 'Rotate key'}
                </button>
              </div>
              {rotateSuccess && (
                <div className="rounded-lg bg-green-50 border border-green-200 px-3 py-2 text-xs text-green-700">
                  ✓ API key rotated. Update your integrations with the new key shown above.
                </div>
              )}
              {rotateError && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
                  {rotateError}
                </div>
              )}
            </div>

            {/* SDK snippet */}
            <div className="card space-y-3">
              <h2 className="text-sm font-semibold text-gray-900">SDK Quick Start</h2>
              <p className="text-xs text-gray-500">Add the snippet below to your website to start tracking events.</p>
              <div className="rounded-lg bg-gray-900 px-4 py-3 text-xs font-mono text-gray-100 space-y-1 overflow-x-auto">
                <p className="text-gray-400">{'<!-- Add before </body> -->'}</p>
                <p>{`<script src="${typeof window !== 'undefined' ? window.location.origin : ''}/sdk/analytics.js"></script>`}</p>
                <p>{`<script>`}</p>
                <p className="pl-4">{`Analytics.init('${data.api_key}', { host: '${typeof window !== 'undefined' ? window.location.origin : 'https://your-domain.com'}' });`}</p>
                <p className="pl-4">{`Analytics.identify('user-123', { plan: 'pro' });`}</p>
                <p className="pl-4">{`Analytics.track('Purchase', { sku: 'PROD-42', price: 29.99 });`}</p>
                <p className="pl-4">{`Analytics.page();`}</p>
                <p>{`</script>`}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import {
  getMe, rotateApiKey, getTeam, inviteMember, removeMember,
  updateMemberRole, cancelInvite,
  ApiError, type TeamMember, type PendingInvite,
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

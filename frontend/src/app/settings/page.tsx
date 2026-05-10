'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { getMe, rotateApiKey, ApiError } from '@/lib/api';

// ── Copy to clipboard helper ──────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for non-HTTPS contexts
      const el = document.createElement('textarea');
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <button
      onClick={handleCopy}
      className="text-xs font-medium text-brand-600 hover:underline ml-2"
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { data, error, isLoading, mutate } = useSWR('me', getMe);

  const [showKey, setShowKey]         = useState(false);
  const [rotating, setRotating]       = useState(false);
  const [rotateError, setRotateError] = useState('');
  const [rotateSuccess, setRotateSuccess] = useState(false);

  async function handleRotate() {
    if (!confirm(
      'Rotate your API key? The current key will stop working immediately. ' +
      'You must update any JS SDK integrations or webhook senders with the new key.',
    )) return;

    setRotating(true);
    setRotateError('');
    setRotateSuccess(false);
    try {
      const result = await rotateApiKey();
      // Update the local SWR cache so the new key shows immediately
      await mutate(prev => prev ? { ...prev, api_key: result.api_key } : prev, false);
      setShowKey(true);
      setRotateSuccess(true);
    } catch (err) {
      setRotateError(err instanceof ApiError ? err.message : 'Rotation failed');
    } finally {
      setRotating(false);
    }
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
            {/* Workspace info */}
            <div className="card space-y-3">
              <h2 className="text-sm font-semibold text-gray-900">Workspace</h2>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Org name</p>
                  <p className="text-gray-900 font-medium">{data.org_name}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Admin email</p>
                  <p className="text-gray-900">{data.email}</p>
                </div>
              </div>
            </div>

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

              {/* SDK snippet */}
              {showKey && (
                <div className="rounded-lg bg-gray-900 px-4 py-3 text-xs font-mono text-gray-100 overflow-x-auto">
                  <p className="text-gray-400 mb-1">{'// JavaScript SDK'}</p>
                  <p>{`Analytics.init('${data.api_key}', { host: window.location.origin });`}</p>
                </div>
              )}

              {/* Rotate */}
              <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                <div>
                  <p className="text-xs font-medium text-gray-700">Rotate API key</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Generates a new key. The old key stops working immediately.
                  </p>
                </div>
                <button
                  onClick={handleRotate}
                  disabled={rotating}
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

            {/* SDK usage guide */}
            <div className="card space-y-3">
              <h2 className="text-sm font-semibold text-gray-900">SDK Quick Start</h2>
              <p className="text-xs text-gray-500">
                Add the snippet below to your website to start tracking events.
              </p>
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

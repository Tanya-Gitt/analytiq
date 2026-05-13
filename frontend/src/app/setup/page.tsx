'use client';

import { useState, useEffect } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import { getMe, getSetupStatus, type SetupStatus } from '@/lib/api';

// ── helpers ───────────────────────────────────────────────────────────────────

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function fmtNumber(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

// ── Copy button (dark background — used inside CodeBlock header) ──────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(text).then(
      () => { setCopied(true); setTimeout(() => setCopied(false), 2000); },
      () => {
        // Fallback for non-HTTPS
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      },
    );
  }
  return (
    <button
      onClick={copy}
      className="shrink-0 text-xs px-2.5 py-1 rounded-md font-medium transition-colors
                 bg-white/10 hover:bg-white/20 text-gray-300 hover:text-white border border-white/10"
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

// ── API key inline copy (light background) ────────────────────────────────────

function ApiKeyCopy({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(text).then(
      () => { setCopied(true); setTimeout(() => setCopied(false), 2000); },
      () => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      },
    );
  }
  return (
    <button
      onClick={copy}
      className={`shrink-0 text-xs px-3 py-1.5 rounded-lg font-medium transition-colors border ${
        copied
          ? 'bg-green-50 text-green-700 border-green-200'
          : 'bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-200'
      }`}
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

// ── Code block ────────────────────────────────────────────────────────────────

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="relative rounded-xl bg-gray-900 border border-gray-700 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex gap-1.5">
          <span className="w-3 h-3 rounded-full bg-red-500/60" />
          <span className="w-3 h-3 rounded-full bg-yellow-500/60" />
          <span className="w-3 h-3 rounded-full bg-green-500/60" />
        </div>
        <CopyButton text={code} />
      </div>
      <pre className="p-4 text-xs leading-relaxed overflow-x-auto text-gray-100 font-mono">
        <code>{code}</code>
      </pre>
    </div>
  );
}

// ── Snippets ──────────────────────────────────────────────────────────────────

function snippets(apiKey: string, host: string) {
  return {
    Browser: `<!-- Add before </body> -->
<script src="${host}/sdk/analytics.js"></script>
<script>
  Analytics.init('${apiKey}', { host: '${host}' });

  // Identify the logged-in user
  Analytics.identify('user-123', { email: 'alice@example.com' });

  // Track an event
  Analytics.track('Purchase', { sku: 'PROD-1', price: 29.99 });

  // Record a page view
  Analytics.page({ url: window.location.href });
</script>`,

    Python: `pip install analytiq  # or: pip install ./sdk/python

from analytiq import Analytics

client = Analytics('${apiKey}', host='${host}')

client.track('purchase',
    user_id='u_123',
    properties={'sku': 'PROD-1', 'price': 29.99})

client.identify('u_123', {'email': 'alice@example.com', 'plan': 'pro'})
client.page(user_id='u_123', properties={'url': '/checkout'})`,

    'Node.js': `npm install @analytiq/node  # or: npm install ./sdk/node

import { Analytics } from '@analytiq/node';

const client = new Analytics('${apiKey}', { host: '${host}' });

await client.track('purchase', {
  userId: 'u_123',
  properties: { sku: 'PROD-1', price: 29.99 },
});
await client.identify('u_123', { email: 'alice@example.com' });
await client.page({ userId: 'u_123', properties: { url: '/checkout' } });`,

    Go: `go get github.com/your-org/analytiq-go

import "github.com/your-org/analytiq-go/analytiq"

client := analytiq.New("${apiKey}",
    analytiq.WithHost("${host}"),
)

client.Track(ctx, "purchase", analytiq.Opts{
    UserID:     "u_123",
    Properties: map[string]any{"sku": "PROD-1", "price": 29.99},
})
client.Identify(ctx, "u_123", map[string]any{"email": "alice@example.com"})
client.Page(ctx, analytiq.Opts{UserID: "u_123"})`,

    Ruby: `gem 'analytiq', path: './sdk/ruby'

require 'analytiq'

client = Analytiq::Client.new('${apiKey}', host: '${host}')

client.track('purchase',
  user_id: 'u_123',
  properties: { sku: 'PROD-1', price: 29.99 })
client.identify('u_123', email: 'alice@example.com', plan: 'pro')
client.page(user_id: 'u_123', properties: { url: '/checkout' })`,
  };
}

const LANGS = ['Browser', 'Python', 'Node.js', 'Go', 'Ruby'] as const;
type Lang = typeof LANGS[number];

const LANG_COLORS: Record<Lang, string> = {
  Browser: 'text-yellow-400',
  Python:  'text-blue-400',
  'Node.js': 'text-green-400',
  Go:      'text-cyan-400',
  Ruby:    'text-red-400',
};

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBanner({ status, loading }: { status: SetupStatus | undefined; loading: boolean }) {
  if (loading && !status) {
    return (
      <div className="rounded-2xl border border-gray-100 bg-gray-50 px-5 py-4 flex items-center gap-3">
        <div className="w-2.5 h-2.5 rounded-full bg-gray-300 animate-pulse" />
        <span className="text-sm text-gray-400">Checking for events…</span>
      </div>
    );
  }

  const hasEvents = !!status?.last_event_at;

  return (
    <div className={`rounded-2xl border px-5 py-4 flex items-center justify-between gap-4 ${
      hasEvents
        ? 'border-green-100 bg-green-50'
        : 'border-amber-100 bg-amber-50'
    }`}>
      <div className="flex items-center gap-3">
        <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${
          hasEvents ? 'bg-green-500 animate-pulse' : 'bg-amber-400'
        }`} />
        <div>
          {hasEvents ? (
            <>
              <p className="text-sm font-semibold text-green-800">Receiving events</p>
              <p className="text-xs text-green-700 mt-0.5">
                Last: <span className="font-medium">{status!.last_event_name}</span>
                {' '}· {relTime(status!.last_event_at!)}
              </p>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold text-amber-800">Waiting for first event</p>
              <p className="text-xs text-amber-700 mt-0.5">
                Copy a snippet below, send one event, and this will turn green.
              </p>
            </>
          )}
        </div>
      </div>

      {hasEvents && (
        <div className="text-right shrink-0">
          <p className="text-2xl font-bold text-green-700 tabular-nums">
            {fmtNumber(status!.total_events)}
          </p>
          <p className="text-xs text-green-600">total events</p>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SetupPage() {
  const [lang,    setLang]    = useState<Lang>('Browser');
  const [host,    setHost]    = useState('');
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setHost(window.location.origin);
    }
  }, []);

  const { data: me } = useSWR('me', getMe, { revalidateOnFocus: false });
  const { data: status, isLoading } = useSWR('setup-status', getSetupStatus, {
    refreshInterval: 10_000,
  });

  const apiKey      = me?.api_key ?? '';
  const maskedKey   = apiKey ? '•'.repeat(24) + apiKey.slice(-8) : '…loading…';
  // Code snippets show the real key only when the user explicitly reveals it
  const snippetKey  = showKey ? (apiKey || 'YOUR_API_KEY') : 'YOUR_API_KEY';
  const code        = snippets(snippetKey, host || 'https://your-host.com');

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto space-y-6">

        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">SDK Setup</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Send events from your browser or backend in under 2 minutes.
          </p>
        </div>

        {/* Live status */}
        <StatusBanner status={status} loading={isLoading} />

        {/* API key */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">
            Your API Key
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono text-sm bg-gray-50 border border-gray-200
                             rounded-xl px-4 py-2.5 text-gray-800 overflow-x-auto tracking-wider">
              {showKey ? apiKey || '…loading…' : maskedKey}
            </code>

            {/* Show / hide toggle */}
            <button
              onClick={() => setShowKey(v => !v)}
              title={showKey ? 'Hide key' : 'Reveal key'}
              className="shrink-0 p-2 rounded-lg text-gray-400 hover:text-gray-700
                         hover:bg-gray-100 transition-colors border border-gray-200"
            >
              {showKey ? (
                /* eye-slash */
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                </svg>
              ) : (
                /* eye */
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              )}
            </button>

            <ApiKeyCopy text={apiKey || ''} />
          </div>
          <p className="mt-2 text-xs text-gray-400">
            Keep this secret — it identifies your org. Reveal to copy, then store safely.
          </p>
        </div>

        {/* Language tabs + code */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-gray-100 px-4 pt-3 gap-1">
            {LANGS.map(l => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
                  lang === l
                    ? `border-indigo-500 ${LANG_COLORS[l]} bg-gray-50`
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {l}
              </button>
            ))}
          </div>

          {/* Code block */}
          <div className="p-4">
            <CodeBlock code={code[lang]} />
          </div>
        </div>

        {/* Quick reference */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
            Event types
          </p>
          <div className="grid grid-cols-3 gap-3 text-sm">
            {[
              { name: 'track',    desc: 'Named action — purchase, click, signup' },
              { name: 'identify', desc: 'Link a user_id to email, plan, traits'  },
              { name: 'page',     desc: 'Page view with optional URL + metadata' },
            ].map(e => (
              <div key={e.name} className="rounded-xl bg-gray-50 border border-gray-100 p-3">
                <code className="text-xs font-mono font-semibold text-indigo-600">{e.name}</code>
                <p className="mt-1 text-xs text-gray-500 leading-relaxed">{e.desc}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-gray-400">
            Max 50 properties per event · 3 levels deep · 100 events/s rate limit
          </p>
        </div>

      </div>
    </AppShell>
  );
}

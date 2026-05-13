'use client';

import { useState, useEffect } from 'react';
import {
  listShareTokens, createShareToken, revokeShareToken,
  type ShareToken,
} from '@/lib/api';

interface Props {
  segment: 'A' | 'B';
  onClose: () => void;
}

export default function ShareModal({ segment, onClose }: Props) {
  const [tokens, setTokens]   = useState<ShareToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied]   = useState<string | null>(null);

  // form state
  const [days, setDays]   = useState(30);
  const [label, setLabel] = useState('');

  useEffect(() => {
    listShareTokens()
      .then(ts => setTokens(ts.filter(t => t.segment === segment)))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [segment]);

  async function handleCreate() {
    setCreating(true);
    try {
      const t = await createShareToken({ segment, days, label: label.trim() });
      setTokens(prev => [t, ...prev]);
      setLabel('');
    } catch (e: unknown) {
      alert((e as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(token: string) {
    if (!confirm('Revoke this share link? Anyone using it will lose access.')) return;
    await revokeShareToken(token);
    setTokens(prev => prev.filter(t => t.token !== token));
  }

  function copyLink(token: string) {
    const url = `${window.location.origin}/share/${token}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(token);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-900">
            Share Dashboard
            <span className="ml-2 text-xs font-normal bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full">
              Segment {segment}
            </span>
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
        </div>

        {/* Create form */}
        <div className="bg-gray-50 rounded-xl p-4 mb-5">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">
            Create new link
          </p>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              placeholder="Label (optional)"
              value={label}
              onChange={e => setLabel(e.target.value)}
              className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
              maxLength={120}
            />
            <select
              value={days}
              onChange={e => setDays(Number(e.target.value))}
              className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              {[7, 14, 30, 60, 90].map(d => (
                <option key={d} value={d}>{d}d window</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleCreate}
            disabled={creating}
            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-medium rounded-lg py-2 transition-colors"
          >
            {creating ? 'Creating…' : 'Create share link'}
          </button>
        </div>

        {/* Existing tokens */}
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
            Active links
          </p>
          {loading ? (
            <p className="text-sm text-gray-400 py-4 text-center">Loading…</p>
          ) : tokens.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">No share links yet</p>
          ) : (
            <ul className="space-y-2 max-h-64 overflow-y-auto">
              {tokens.map(t => (
                <li key={t.id} className="flex items-center gap-2 bg-gray-50 rounded-xl p-3">
                  <div className="flex-1 min-w-0">
                    {t.label && (
                      <p className="text-xs font-medium text-gray-700 truncate">{t.label}</p>
                    )}
                    <p className="text-xs text-gray-400 font-mono truncate">
                      /share/{t.token.slice(0, 12)}…
                    </p>
                    <p className="text-xs text-gray-400">{t.days}d · created {t.created_at.slice(0, 10)}</p>
                  </div>
                  <button
                    onClick={() => copyLink(t.token)}
                    className="shrink-0 text-xs bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-medium px-2.5 py-1.5 rounded-lg transition-colors"
                  >
                    {copied === t.token ? '✓ Copied' : 'Copy'}
                  </button>
                  <button
                    onClick={() => handleRevoke(t.token)}
                    className="shrink-0 text-xs bg-red-50 hover:bg-red-100 text-red-600 font-medium px-2.5 py-1.5 rounded-lg transition-colors"
                  >
                    Revoke
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

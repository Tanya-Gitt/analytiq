'use client';

import { useState, FormEvent } from 'react';
import { createPortal } from 'react-dom';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import {
  listFlags, createFlag, updateFlag, deleteFlag,
  type FeatureFlag,
} from '@/lib/api';
import ConfirmDialog from '@/components/ConfirmDialog';

// ── helpers ────────────────────────────────────────────────────────────────────

function relTime(iso: string) {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return d === 0 ? 'today' : d === 1 ? 'yesterday' : `${d}d ago`;
}

// ── Rollout slider ────────────────────────────────────────────────────────────

function RolloutBar({ pct }: { pct: number }) {
  const color = pct === 100 ? 'bg-green-500' : pct === 0 ? 'bg-gray-200' : 'bg-indigo-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-gray-500 w-8 text-right">{pct}%</span>
    </div>
  );
}

// ── Flag row ──────────────────────────────────────────────────────────────────

function FlagRow({
  flag,
  onToggle,
  onEdit,
  onDelete,
}: {
  flag: FeatureFlag;
  onToggle: (flag: FeatureFlag) => void;
  onEdit:   (flag: FeatureFlag) => void;
  onDelete: (flag: FeatureFlag) => void;
}) {
  return (
    <div className="flex items-center gap-4 py-4 border-b border-gray-50 last:border-0">
      {/* Toggle */}
      <button
        onClick={() => onToggle(flag)}
        className={`relative w-10 h-5 rounded-full transition-colors shrink-0 ${
          flag.enabled ? 'bg-indigo-500' : 'bg-gray-200'
        }`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
          flag.enabled ? 'translate-x-5' : 'translate-x-0'
        }`} />
      </button>

      {/* Name + description */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <code className="text-sm font-mono font-semibold text-gray-800">{flag.name}</code>
          {flag.targeting.length > 0 && (
            <span className="text-xs bg-violet-50 text-violet-600 border border-violet-100 px-1.5 py-0.5 rounded-md font-medium">
              {flag.targeting.length} rule{flag.targeting.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        {flag.description && (
          <p className="text-xs text-gray-400 mt-0.5 truncate">{flag.description}</p>
        )}
      </div>

      {/* Rollout */}
      <div className="w-36 shrink-0">
        <RolloutBar pct={flag.rollout_pct} />
      </div>

      {/* Updated */}
      <span className="text-xs text-gray-400 shrink-0 w-16 text-right">
        {relTime(flag.updated_at)}
      </span>

      {/* Actions */}
      <div className="flex gap-1 shrink-0">
        <button
          onClick={() => onEdit(flag)}
          className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
          </svg>
        </button>
        <button
          onClick={() => onDelete(flag)}
          className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
          </svg>
        </button>
      </div>
    </div>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────────────

function FlagModal({
  flag,
  onClose,
  onSave,
}: {
  flag: Partial<FeatureFlag> | null;
  onClose: () => void;
  onSave:  (data: Partial<FeatureFlag>) => Promise<void>;
}) {
  const isNew = !flag?.id;
  const [name,        setName]        = useState(flag?.name        ?? '');
  const [description, setDescription] = useState(flag?.description ?? '');
  const [enabled,     setEnabled]     = useState(flag?.enabled     ?? false);
  const [rollout,     setRollout]     = useState(flag?.rollout_pct ?? 0);
  const [saving,      setSaving]      = useState(false);
  const [error,       setError]       = useState('');

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await onSave({ name, description, enabled, rollout_pct: rollout });
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
        <h2 className="text-base font-bold text-gray-900 mb-4">
          {isNew ? 'Create flag' : 'Edit flag'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {isNew && (
            <div>
              <label className="text-xs font-semibold text-gray-500 block mb-1">
                Flag key <span className="font-normal text-gray-400">(lowercase, hyphens)</span>
              </label>
              <input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="new-checkout-flow"
                pattern="[a-z0-9-_]+"
                required
                className="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm font-mono
                           focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-gray-500 block mb-1">Description</label>
            <input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="What does this flag control?"
              className="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm
                         focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setEnabled(v => !v)}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                enabled ? 'bg-indigo-500' : 'bg-gray-200'
              }`}
            >
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                enabled ? 'translate-x-5' : ''
              }`} />
            </button>
            <span className="text-sm text-gray-700">{enabled ? 'Enabled' : 'Disabled'}</span>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-gray-500">Rollout</label>
              <span className="text-xs font-mono text-indigo-600">{rollout}%</span>
            </div>
            <input
              type="range" min={0} max={100} step={5}
              value={rollout}
              onChange={e => setRollout(Number(e.target.value))}
              className="w-full accent-indigo-500"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5">
              <span>Off</span>
              <span>50%</span>
              <span>Everyone</span>
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-xl px-3 py-2">{error}</p>
          )}

          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 py-2 rounded-xl border border-gray-200 text-sm text-gray-600 hover:bg-gray-50">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium
                         hover:bg-indigo-700 disabled:opacity-50">
              {saving ? 'Saving…' : isNew ? 'Create' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

// Stable sort: newest first, then alphabetical — matches backend ORDER BY
function stableSort(list: FeatureFlag[]): FeatureFlag[] {
  return [...list].sort((a, b) => {
    const td = new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    if (td !== 0) return td;
    return a.name.localeCompare(b.name);
  });
}

export default function FlagsPage() {
  const { data: rawFlags, isLoading, mutate } = useSWR('flags', listFlags, { refreshInterval: 30_000 });
  const [modal,  setModal]  = useState<Partial<FeatureFlag> | null | false>(false);
  const [deleting, setDeleting] = useState<FeatureFlag | null>(null);

  // Always render in stable order so server re-fetches never shuffle the list
  const flags = rawFlags ? stableSort(rawFlags) : rawFlags;

  async function handleToggle(flag: FeatureFlag) {
    // Optimistic: flip the flag in-place, preserve current sorted order
    mutate(
      flags?.map(f => f.id === flag.id ? { ...f, enabled: !f.enabled } : f),
      false,
    );
    try {
      await updateFlag(flag.id, { enabled: !flag.enabled });
    } finally {
      mutate(); // sync with server
    }
  }

  async function handleSave(data: Partial<FeatureFlag>) {
    if (modal && 'id' in modal && modal.id) {
      // Optimistic: patch the edited flag in-place
      mutate(
        flags?.map(f => f.id === (modal as FeatureFlag).id ? { ...f, ...data } : f),
        false,
      );
      await updateFlag(modal.id, data);
    } else {
      await createFlag(data as Parameters<typeof createFlag>[0]);
    }
    mutate();
  }

  async function handleDelete(flag: FeatureFlag) {
    await deleteFlag(flag.id);
    setDeleting(null);
    mutate(flags?.filter(f => f.id !== flag.id), false);
    mutate();
  }

  const total    = flags?.length ?? 0;
  const active   = flags?.filter(f => f.enabled).length ?? 0;

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Feature Flags</h1>
            <p className="mt-0.5 text-sm text-gray-500">
              Gradual rollouts · targeting rules · A/B experimentation
            </p>
          </div>
          <button
            onClick={() => setModal({})}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white
                       text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            New flag
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Total flags',   value: total  },
            { label: 'Active',        value: active, color: 'text-green-600'  },
            { label: 'Inactive',      value: total - active, color: 'text-gray-400' },
          ].map(s => (
            <div key={s.label} className="bg-white rounded-2xl border border-gray-100 shadow-sm px-5 py-4">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-widest mb-1">{s.label}</p>
              <p className={`text-3xl font-bold tabular-nums ${s.color ?? 'text-gray-800'}`}>{s.value}</p>
            </div>
          ))}
        </div>

        {/* Evaluate snippet */}
        <div className="bg-indigo-50 border border-indigo-100 rounded-2xl px-5 py-4">
          <p className="text-xs font-semibold text-indigo-700 uppercase tracking-widest mb-2">
            SDK usage
          </p>
          <pre className="text-xs text-indigo-900 font-mono leading-relaxed overflow-x-auto">{`# Check flags server-side (Python)
import httpx
flags = httpx.post(
    "http://your-host/api/flags/evaluate",
    headers={"Authorization": "Bearer YOUR_JWT"},
    json={"user_id": "u_123", "attributes": {"plan": "pro"}},
).json()
# → {"new-checkout-flow": True, "dark-mode": False, ...}`}</pre>
        </div>

        {/* Flag list */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-6 py-2">
          {isLoading && (
            <div className="py-12 text-center text-sm text-gray-400">Loading…</div>
          )}
          {!isLoading && (!flags || flags.length === 0) && (
            <div className="py-12 text-center space-y-2">
              <p className="text-3xl">🚩</p>
              <p className="text-sm font-medium text-gray-600">No flags yet</p>
              <p className="text-xs text-gray-400">Create your first flag to start rolling out features.</p>
            </div>
          )}
          {flags?.map(flag => (
            <FlagRow
              key={flag.id}
              flag={flag}
              onToggle={handleToggle}
              onEdit={f => setModal(f)}
              onDelete={f => setDeleting(f)}
            />
          ))}
        </div>
      </div>

      {/* Create/Edit modal */}
      {modal !== false && (
        <FlagModal
          flag={modal || null}
          onClose={() => setModal(false)}
          onSave={handleSave}
        />
      )}

      <ConfirmDialog
        open={!!deleting}
        title={`Delete flag "${deleting?.name ?? ''}"?`}
        description="This feature flag will be permanently removed. Any code checking this flag will receive the default (off) state."
        confirmWord="delete"
        confirmLabel="Delete flag"
        onConfirm={() => deleting && handleDelete(deleting)}
        onClose={() => setDeleting(null)}
      />
    </AppShell>
  );
}

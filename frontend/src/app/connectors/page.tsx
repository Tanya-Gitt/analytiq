'use client';

import { useRef, useState } from 'react';
import useSWR, { mutate } from 'swr';
import AppShell from '@/components/layout/AppShell';
import {
  listConnectors, createConnector, deleteConnector, getSyncRuns, uploadCsv, triggerSync,
  Connector, SyncRun, ApiError,
} from '@/lib/api';
import clsx from 'clsx';

// ── Connector type metadata ───────────────────────────────────────────────────

const TYPE_LABELS: Record<string, string> = {
  sheets_csv:  'Google Sheets / CSV URL',
  csv_upload:  'CSV Upload',
  webhook:     'Webhook (push)',
  js_sdk:      'JavaScript SDK',
};

// ── Create connector form ─────────────────────────────────────────────────────

function CreateConnectorForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState('sheets_csv');
  const [segment, setSegment] = useState('B');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');           // sheets_csv
  const [secret, setSecret] = useState('');     // webhook
  const [origins, setOrigins] = useState('');   // js_sdk
  const [columnMap, setColumnMap] = useState('');
  const [targetTable, setTargetTable] = useState('orders');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleCreate() {
    setError('');
    setLoading(true);
    try {
      const config: Record<string, unknown> = {};
      if (type === 'sheets_csv')  { config.url = url; config.target_table = targetTable; }
      if (type === 'csv_upload')  { config.target_table = targetTable; }
      if (type === 'webhook')     { config.secret = secret; }
      if (type === 'js_sdk')      {
        config.allowed_origins = origins.split(',').map(s => s.trim()).filter(Boolean);
      }
      if (['sheets_csv', 'csv_upload'].includes(type) && columnMap.trim()) {
        try {
          config.column_map = JSON.parse(columnMap);
        } catch {
          throw new Error('column_map must be valid JSON, e.g. {"Date":"order_date","Qty":"quantity"}');
        }
      }
      await createConnector({ type, segment, name: name || undefined, config });
      onCreated();
      setOpen(false);
      setName(''); setUrl(''); setSecret(''); setOrigins(''); setColumnMap('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn-primary">
        + Add connector
      </button>
    );
  }

  return (
    <div className="card space-y-4 max-w-lg">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">New connector</h3>
        <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Type</label>
          <select value={type} onChange={e => setType(e.target.value)} className="input">
            {Object.entries(TYPE_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Segment</label>
          <select value={segment} onChange={e => setSegment(e.target.value)} className="input">
            <option value="B">B — Orders / Revenue</option>
            <option value="A">A — Events</option>
          </select>
        </div>
      </div>

      <div>
        <label className="label">Name <span className="text-gray-400 font-normal">(optional)</span></label>
        <input className="input" placeholder="My Orders Sheet" value={name} onChange={e => setName(e.target.value)} />
      </div>

      {type === 'sheets_csv' && (
        <div>
          <label className="label">CSV URL</label>
          <input className="input" placeholder="https://docs.google.com/…/export?format=csv"
            value={url} onChange={e => setUrl(e.target.value)} />
        </div>
      )}

      {type === 'webhook' && (
        <div>
          <label className="label">HMAC secret</label>
          <input className="input" type="password" placeholder="super-secret-key"
            value={secret} onChange={e => setSecret(e.target.value)} />
          <p className="text-xs text-gray-400 mt-1">
            Sign requests with <code>HMAC-SHA256(secret, body)</code> → <code>X-Webhook-Signature</code> header
          </p>
        </div>
      )}

      {type === 'js_sdk' && (
        <div>
          <label className="label">Allowed origins</label>
          <input className="input" placeholder="https://myapp.com, https://app.myapp.com"
            value={origins} onChange={e => setOrigins(e.target.value)} />
          <p className="text-xs text-gray-400 mt-1">Comma-separated. Leave blank to allow all origins.</p>
        </div>
      )}

      {['sheets_csv', 'csv_upload'].includes(type) && (
        <>
          <div>
            <label className="label">Target table</label>
            <select value={targetTable} onChange={e => setTargetTable(e.target.value)} className="input">
              <option value="orders">orders (Segment B)</option>
              <option value="custom_rows">custom_rows (Segment A)</option>
            </select>
          </div>
          <div>
            <label className="label">
              Column map <span className="text-gray-400 font-normal">(JSON)</span>
            </label>
            <textarea
              className="input font-mono text-xs h-24 resize-none"
              placeholder={'{\n  "Date": "order_date",\n  "Units": "quantity",\n  "OrderID": "order_id"\n}'}
              value={columnMap}
              onChange={e => setColumnMap(e.target.value)}
            />
          </div>
        </>
      )}

      <div className="flex gap-2 justify-end pt-1">
        <button onClick={() => setOpen(false)} className="btn-secondary">Cancel</button>
        <button onClick={handleCreate} className="btn-primary" disabled={loading}>
          {loading ? 'Creating…' : 'Create connector'}
        </button>
      </div>
    </div>
  );
}

// ── Sync runs drawer ──────────────────────────────────────────────────────────

function SyncRunsPanel({ connector }: { connector: Connector }) {
  const { data, isLoading } = useSWR(
    ['sync-runs', connector.id],
    () => getSyncRuns(connector.id),
    { refreshInterval: 10_000 },
  );

  return (
    <div className="mt-2 space-y-1 text-xs">
      {isLoading && <p className="text-gray-400">Loading runs…</p>}
      {data?.slice(0, 5).map((run: SyncRun) => (
        <div key={run.id} className="flex items-center gap-2 text-gray-600">
          <span className={clsx(
            'inline-block w-2 h-2 rounded-full flex-shrink-0',
            run.status === 'success' ? 'bg-green-400'
              : run.status === 'failed' ? 'bg-red-400'
              : 'bg-yellow-400',
          )} />
          <span className="font-mono">{run.started_at.slice(0, 16)}</span>
          <span>{run.status}</span>
          {run.rows_upserted != null && <span>— {run.rows_upserted} rows</span>}
          {run.error_message && (
            <span className="text-red-500 truncate max-w-xs" title={run.error_message}>
              {run.error_message}
            </span>
          )}
        </div>
      ))}
      {data?.length === 0 && <p className="text-gray-400">No runs yet</p>}
    </div>
  );
}

// ── Connector card ────────────────────────────────────────────────────────────

function ConnectorCard({ connector, onDeleted }: { connector: Connector; onDeleted: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleSyncNow() {
    setSyncing(true);
    setUploadMsg('');
    try {
      await triggerSync(connector.id);
      setUploadMsg('Sync started — check runs below');
      setExpanded(true);
      mutate('connectors');
    } catch (err) {
      setUploadMsg(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSyncing(false);
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete "${connector.name}"? This will remove all sync history and cannot be undone.`)) return;
    setDeleting(true);
    try {
      await deleteConnector(connector.id);
      onDeleted();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : String(err));
      setDeleting(false);
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg('');
    try {
      await uploadCsv(connector.id, file);
      setUploadMsg('Sync started — check runs below');
      setExpanded(true);
      // Revalidate the connectors list so status refreshes
      mutate('connectors');
    } catch (err) {
      setUploadMsg(err instanceof ApiError ? err.message : String(err));
    } finally {
      setUploading(false);
      // Reset file input so the same file can be re-uploaded
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-900 text-sm">{connector.name}</span>
            <span className={`badge-${connector.status}`}>{connector.status}</span>
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
              Seg {connector.segment}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">{TYPE_LABELS[connector.type]}</p>
          {connector.last_synced_at && (
            <p className="text-xs text-gray-400 mt-0.5">
              Last synced: {new Date(connector.last_synced_at).toLocaleString()}
            </p>
          )}
          {connector.last_error && (
            <p className="text-xs text-red-500 mt-0.5 truncate max-w-sm" title={connector.last_error}>
              Error: {connector.last_error}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3 ml-4 flex-shrink-0">
          {/* Manual sync — shown for poll-based connectors (not push) */}
          {['sheets_csv', 'csv_upload'].includes(connector.type) && (
            <button
              onClick={handleSyncNow}
              disabled={syncing}
              className="text-xs text-brand-600 hover:underline disabled:opacity-50"
            >
              {syncing ? 'Syncing…' : '↻ Sync now'}
            </button>
          )}

          {/* CSV file upload — only shown for csv_upload connectors */}
          {connector.type === 'csv_upload' && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={handleFileChange}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="text-xs text-brand-600 hover:underline disabled:opacity-50"
              >
                {uploading ? 'Uploading…' : '↑ Upload CSV'}
              </button>
            </>
          )}
          <button
            onClick={() => setExpanded(v => !v)}
            className="text-xs text-brand-600 hover:underline"
          >
            {expanded ? 'Hide runs' : 'Sync runs'}
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="text-xs text-red-400 hover:text-red-600 disabled:opacity-50"
            title="Delete connector"
          >
            {deleting ? '…' : '✕'}
          </button>
        </div>
      </div>

      {uploadMsg && (
        <p className={clsx(
          'text-xs mt-2',
          uploadMsg.startsWith('Sync') ? 'text-green-600' : 'text-red-500',
        )}>
          {uploadMsg}
        </p>
      )}

      {expanded && <SyncRunsPanel connector={connector} />}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ConnectorsPage() {
  const { data, isLoading, error, mutate: revalidate } = useSWR(
    'connectors',
    listConnectors,
    { refreshInterval: 30_000 },
  );

  return (
    <AppShell>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Connectors</h1>
          <p className="text-sm text-gray-500 mt-0.5">Connect data sources to your workspace</p>
        </div>
        <CreateConnectorForm onCreated={() => revalidate()} />
      </div>

      {isLoading && (
        <div className="space-y-3 animate-pulse">
          {[0, 1, 2].map(i => <div key={i} className="card h-20 bg-gray-100" />)}
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error.message}
        </div>
      )}

      {data && data.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg">No connectors yet</p>
          <p className="text-sm mt-1">Add one above to start importing data</p>
        </div>
      )}

      <div className="space-y-3">
        {data?.map(c => <ConnectorCard key={c.id} connector={c} onDeleted={() => revalidate()} />)}
      </div>
    </AppShell>
  );
}

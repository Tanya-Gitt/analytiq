'use client';

import { useState, useRef, useEffect, FormEvent } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import {
  copilotQuery,
  copilotSuggestions,
  type CopilotQueryResponse,
} from '@/lib/api';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

// ── colour palette ─────────────────────────────────────────────────────────────

const PALETTE = [
  '#6366f1', '#8b5cf6', '#ec4899', '#f59e0b',
  '#10b981', '#3b82f6', '#ef4444', '#14b8a6',
];

// ── helpers ────────────────────────────────────────────────────────────────────

function fmt(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') {
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
    if (v >= 1_000)     return `${(v / 1_000).toFixed(1)}k`;
    return v % 1 === 0 ? String(v) : v.toFixed(2);
  }
  return String(v);
}

// ── Chart renderer ─────────────────────────────────────────────────────────────

function CopilotChart({ result }: { result: CopilotQueryResponse }) {
  const { chart_type, x_key, y_key, columns, rows } = result;

  // Build a list of plain objects from rows+columns
  const data = rows.map(row => {
    const obj: Record<string, unknown> = {};
    columns.forEach((col, i) => { obj[col] = row[i]; });
    return obj;
  });

  // ── Single number ──────────────────────────────────────────────────────────
  if (chart_type === 'number') {
    const val = data[0]?.[y_key] ?? data[0]?.[columns[0]];
    return (
      <div className="flex flex-col items-center justify-center py-10">
        <p className="text-6xl font-bold text-indigo-600 tabular-nums">{fmt(val)}</p>
        <p className="mt-2 text-sm text-gray-500">{y_key || columns[0]}</p>
      </div>
    );
  }

  // ── Table ──────────────────────────────────────────────────────────────────
  if (chart_type === 'table') {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b border-gray-100">
              {columns.map(col => (
                <th key={col} className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className="border-b border-gray-50 hover:bg-gray-50">
                {row.map((cell, ci) => (
                  <td key={ci} className="px-3 py-2 text-gray-700 whitespace-nowrap">
                    {String(cell ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="text-center py-8 text-sm text-gray-400">No rows returned</p>
        )}
      </div>
    );
  }

  // ── Pie / donut ────────────────────────────────────────────────────────────
  if (chart_type === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie
            data={data}
            dataKey={y_key}
            nameKey={x_key}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            paddingAngle={2}
            label={({ name, percent }) =>
              `${name} ${(percent * 100).toFixed(0)}%`
            }
            labelLine={false}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(v: unknown) => fmt(v)} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  // ── Line ───────────────────────────────────────────────────────────────────
  if (chart_type === 'line') {
    return (
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <XAxis
            dataKey={x_key}
            tick={{ fontSize: 11, fill: '#9ca3af' }}
            tickFormatter={v => String(v).slice(0, 10)}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#9ca3af' }}
            tickFormatter={v => fmt(v)}
            width={56}
          />
          <Tooltip formatter={(v: unknown) => fmt(v)} />
          <Line
            type="monotone"
            dataKey={y_key}
            stroke={PALETTE[0]}
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  // ── Bar (default) ──────────────────────────────────────────────────────────
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
        <XAxis
          dataKey={x_key}
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          tickFormatter={v => String(v).slice(0, 14)}
        />
        <YAxis
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          tickFormatter={v => fmt(v)}
          width={56}
        />
        <Tooltip formatter={(v: unknown) => fmt(v)} />
        <Bar dataKey={y_key} radius={[4, 4, 0, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Result card ────────────────────────────────────────────────────────────────

function ResultCard({ result }: { result: CopilotQueryResponse }) {
  const [showSql, setShowSql] = useState(false);

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-50">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-widest text-gray-400 mb-0.5">
              {result.chart_type.toUpperCase()}
            </p>
            <h3 className="text-base font-semibold text-gray-800">{result.title}</h3>
          </div>
          <button
            onClick={() => setShowSql(v => !v)}
            className="shrink-0 text-xs text-gray-400 hover:text-indigo-600 transition-colors px-2 py-1 rounded-lg hover:bg-indigo-50"
          >
            {showSql ? 'Hide SQL' : 'View SQL'}
          </button>
        </div>

        {/* Insight */}
        <p className="mt-2 text-sm text-gray-600 leading-relaxed">{result.insight}</p>
      </div>

      {/* SQL collapse */}
      {showSql && (
        <div className="px-6 py-3 bg-gray-50 border-b border-gray-100">
          <pre className="text-xs text-gray-700 font-mono whitespace-pre-wrap leading-relaxed">
            {result.sql}
          </pre>
        </div>
      )}

      {/* Chart / table */}
      <div className="px-6 py-4">
        <CopilotChart result={result} />
      </div>

      {/* Row count */}
      {result.rows.length > 0 && (
        <div className="px-6 pb-4 text-xs text-gray-400">
          {result.rows.length} row{result.rows.length !== 1 ? 's' : ''} returned
        </div>
      )}
    </div>
  );
}

// ── Message types ──────────────────────────────────────────────────────────────

interface UserMessage  { role: 'user';      text: string }
interface AssistantMsg { role: 'assistant'; result: CopilotQueryResponse }
interface ErrorMsg     { role: 'error';     text: string }
type Message = UserMessage | AssistantMsg | ErrorMsg;

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CopilotPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput]       = useState('');
  const [loading, setLoading]   = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: suggestionsData } = useSWR('copilot-suggestions', copilotSuggestions, {
    revalidateOnFocus: false,
  });
  const suggestions = suggestionsData?.suggestions ?? [];

  // Scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function submit(question: string) {
    if (!question.trim() || loading) return;
    const q = question.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text: q }]);
    setLoading(true);
    try {
      const result = await copilotQuery(q);
      setMessages(prev => [...prev, { role: 'assistant', result }]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setMessages(prev => [...prev, { role: 'error', text: msg }]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    submit(input);
  }

  const isEmpty = messages.length === 0;

  return (
    <AppShell>
      <div className="flex flex-col h-[calc(100vh-0px)] max-h-screen">

        {/* ── Header ── */}
        <div className="px-6 pt-6 pb-4 border-b border-gray-100 bg-white shrink-0">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center shrink-0">
                <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                </svg>
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-900 leading-none">AI Copilot</h1>
                <p className="text-xs text-gray-500 mt-0.5">Ask anything about your data — powered by Claude</p>
              </div>
            </div>
          </div>
        </div>

        {/* ── Message area ── */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="max-w-3xl mx-auto space-y-6">

            {/* Empty state + suggestions */}
            {isEmpty && (
              <div className="space-y-6">
                <div className="text-center py-8">
                  <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center mx-auto mb-4">
                    <svg className="w-8 h-8 text-indigo-500" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round"
                        d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                    </svg>
                  </div>
                  <h2 className="text-lg font-semibold text-gray-800">Ask about your data</h2>
                  <p className="mt-1 text-sm text-gray-500 max-w-sm mx-auto">
                    Type any question in plain English. The AI writes the SQL, runs it against your data, and renders the best chart.
                  </p>
                </div>

                {suggestions.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
                      Try asking…
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {suggestions.slice(0, 8).map(s => (
                        <button
                          key={s}
                          onClick={() => submit(s)}
                          className="text-left px-4 py-3 rounded-xl border border-gray-100 bg-white
                                     text-sm text-gray-700 hover:border-indigo-200 hover:bg-indigo-50
                                     hover:text-indigo-700 transition-colors shadow-sm"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Messages */}
            {messages.map((msg, i) => {
              if (msg.role === 'user') {
                return (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-lg px-4 py-3 rounded-2xl rounded-tr-sm bg-indigo-600 text-white text-sm leading-relaxed shadow-sm">
                      {msg.text}
                    </div>
                  </div>
                );
              }
              if (msg.role === 'error') {
                return (
                  <div key={i} className="bg-red-50 border border-red-100 rounded-2xl px-5 py-4">
                    <p className="text-sm font-medium text-red-700 mb-1">Something went wrong</p>
                    <p className="text-xs text-red-600">{msg.text}</p>
                  </div>
                );
              }
              return (
                <ResultCard key={i} result={msg.result} />
              );
            })}

            {/* Loading indicator */}
            {loading && (
              <div className="flex items-center gap-3 text-sm text-gray-500">
                <div className="flex gap-1">
                  <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" />
                </div>
                Thinking…
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </div>

        {/* ── Input bar ── */}
        <div className="shrink-0 border-t border-gray-100 bg-white px-6 py-4">
          <div className="max-w-3xl mx-auto">
            <form onSubmit={handleSubmit} className="flex gap-3">
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Ask about your data… e.g. "Which channels drove the most revenue?""
                disabled={loading}
                className="flex-1 px-4 py-3 rounded-xl border border-gray-200 text-sm
                           placeholder:text-gray-400 focus:outline-none focus:ring-2
                           focus:ring-indigo-500 focus:border-transparent
                           disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="px-5 py-3 rounded-xl bg-indigo-600 text-white text-sm font-medium
                           hover:bg-indigo-700 transition-colors disabled:opacity-40
                           disabled:cursor-not-allowed flex items-center gap-2 shrink-0"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                </svg>
                Ask
              </button>
            </form>
            <p className="mt-2 text-xs text-gray-400 text-center">
              Queries run read-only against your org's data only · max 500 rows
            </p>
          </div>
        </div>

      </div>
    </AppShell>
  );
}

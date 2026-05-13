'use client';

import { useState } from 'react';
import useSWR from 'swr';
import AppShell from '@/components/layout/AppShell';
import {
  listHeatmapPages,
  getHeatmapClicks,
  getHeatmapScroll,
  type HeatmapPage,
} from '@/lib/api';

// ── Colour scale (cold → hot) ─────────────────────────────────────────────────

function cellColor(v: number): string {
  if (v === 0)  return 'bg-slate-100';
  if (v < 12)   return 'bg-blue-100';
  if (v < 25)   return 'bg-cyan-200';
  if (v < 40)   return 'bg-teal-300';
  if (v < 55)   return 'bg-yellow-300';
  if (v < 70)   return 'bg-orange-400';
  if (v < 85)   return 'bg-red-500';
  return 'bg-red-700';
}

const LEGEND_SWATCHES = [
  'bg-slate-100 border border-slate-200',
  'bg-blue-100', 'bg-cyan-200', 'bg-teal-300',
  'bg-yellow-300', 'bg-orange-400', 'bg-red-700',
];

interface GridCell { row: number; col: number; intensity: number; count: number }

function ClickGrid({ cells, total }: { cells: GridCell[]; total: number }) {
  const matrix: number[][] = Array.from({ length: 10 }, () => Array(10).fill(0));
  const counts: number[][] = Array.from({ length: 10 }, () => Array(10).fill(0));
  for (const c of cells) {
    if (c.row >= 0 && c.row < 10 && c.col >= 0 && c.col < 10) {
      matrix[c.row][c.col] = c.intensity;
      counts[c.row][c.col] = c.count;
    }
  }

  if (total === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-gray-400 text-sm">
        <p className="text-2xl mb-2">🖱️</p>
        No click data yet.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {/* Top axis */}
      <div className="flex items-center text-[10px] text-gray-400 px-0.5">
        <span>← left</span>
        <span className="flex-1" />
        <span>right →</span>
      </div>

      {/* Grid + left axis */}
      <div className="flex gap-1.5">
        {/* Y-axis */}
        <div className="flex flex-col justify-between text-[10px] text-gray-400 text-right shrink-0 w-6 py-0.5">
          <span>top</span>
          <span>mid</span>
          <span>btm</span>
        </div>

        {/* 10×10 cells */}
        <div
          className="flex-1 grid gap-0.5"
          style={{ gridTemplateColumns: 'repeat(10, 1fr)' }}
        >
          {matrix.flatMap((row, ri) =>
            row.map((intensity, ci) => (
              <div
                key={`${ri}-${ci}`}
                title={`(${ci * 10}–${ci * 10 + 10}% L, ${ri * 10}–${ri * 10 + 10}% T) · ${counts[ri][ci]} clicks`}
                className={`aspect-square rounded-sm ${cellColor(intensity)}`}
              />
            ))
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-1.5 pt-0.5">
        <span className="text-[10px] text-gray-400">Cold</span>
        {LEGEND_SWATCHES.map((cls, i) => (
          <div key={i} className={`w-4 h-2.5 rounded-sm ${cls}`} />
        ))}
        <span className="text-[10px] text-gray-400">Hot</span>
        <span className="ml-auto text-[10px] text-gray-400">{total.toLocaleString()} clicks</span>
      </div>
    </div>
  );
}

// ── Scroll depth ──────────────────────────────────────────────────────────────

interface ScrollBucket { depth: number; sessions: number; pct: number }

function ScrollChart({ buckets, total }: { buckets: ScrollBucket[]; total: number }) {
  if (total === 0 || buckets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-gray-400 text-sm">
        <p className="text-2xl mb-1">📜</p>
        No scroll data yet.
      </div>
    );
  }

  const map    = new Map(buckets.map(b => [b.depth, b]));
  const maxPct = Math.max(...buckets.map(b => b.pct), 1);

  return (
    <div className="space-y-1">
      {[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map(depth => {
        const b   = map.get(depth);
        const pct = b?.pct ?? 0;
        const rel = (pct / maxPct) * 100;
        const color = rel > 70 ? 'bg-indigo-500' : rel > 40 ? 'bg-indigo-400' : rel > 15 ? 'bg-indigo-300' : 'bg-gray-200';
        return (
          <div key={depth} className="flex items-center gap-1.5">
            <span className="text-[10px] text-gray-400 w-7 text-right shrink-0">{depth}%</span>
            <div className="flex-1 h-3 bg-gray-50 rounded overflow-hidden">
              <div className={`h-full rounded ${color}`} style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[10px] text-gray-500 w-8 tabular-nums">{pct}%</span>
          </div>
        );
      })}
      <p className="text-[10px] text-gray-400 text-right pt-0.5">{total.toLocaleString()} sessions</p>
    </div>
  );
}

// ── Page list ─────────────────────────────────────────────────────────────────

function PageList({ pages, selected, onSelect }: {
  pages:    HeatmapPage[];
  selected: string;
  onSelect: (url: string) => void;
}) {
  if (pages.length === 0) {
    return (
      <div className="text-xs text-gray-400 text-center py-6">
        No pages tracked yet.<br />Add the JS SDK snippet to start capturing.
      </div>
    );
  }
  return (
    <div className="space-y-0.5">
      {pages.map(p => {
        const path = (() => { try { return new URL(p.page_url).pathname || p.page_url; } catch { return p.page_url; } })();
        return (
          <button
            key={p.page_url}
            onClick={() => onSelect(p.page_url)}
            className={`w-full text-left px-3 py-2 rounded-xl text-sm transition-colors ${
              selected === p.page_url
                ? 'bg-indigo-50 text-indigo-700 font-medium'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <p className="font-mono text-xs truncate">{path}</p>
            <p className="text-[10px] text-gray-400 mt-0.5">
              {p.clicks.toLocaleString()} clicks · {p.scrolls.toLocaleString()} scrolls
            </p>
          </button>
        );
      })}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function HeatmapsPage() {
  const [selectedUrl, setSelectedUrl] = useState('');
  const [days, setDays]               = useState(30);

  const { data: pages } = useSWR('heatmap-pages', listHeatmapPages, { refreshInterval: 60_000 });

  const { data: clickData } = useSWR(
    selectedUrl ? ['heatmap-clicks', selectedUrl, days] : null,
    () => getHeatmapClicks(selectedUrl, days),
  );

  const { data: scrollData } = useSWR(
    selectedUrl ? ['heatmap-scroll', selectedUrl, days] : null,
    () => getHeatmapScroll(selectedUrl, days),
  );

  const pageList  = pages ?? [];
  const pagePath  = (() => { try { return new URL(selectedUrl).pathname; } catch { return selectedUrl; } })();

  return (
    <AppShell>
      <div className="max-w-7xl mx-auto flex flex-col gap-4" style={{ minHeight: 0 }}>

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Heatmaps</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Where users click · how far they scroll
            </p>
          </div>
          <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
            {[7, 30, 90].map(d => (
              <button key={d} onClick={() => setDays(d)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  days === d ? 'bg-white text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}>
                {d}d
              </button>
            ))}
          </div>
        </div>

        {/* Main layout: pages list + charts */}
        <div className="grid grid-cols-[200px_1fr] gap-4 items-start">

          {/* Pages sidebar */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-3">
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-2">Pages</p>
            <PageList pages={pageList} selected={selectedUrl} onSelect={setSelectedUrl} />
          </div>

          {/* Charts area */}
          {!selectedUrl ? (
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm flex flex-col
                            items-center justify-center py-20 text-gray-400">
              <p className="text-3xl mb-2">👈</p>
              <p className="text-sm font-medium text-gray-600">Select a page to view its heatmap</p>
              <p className="text-xs text-gray-400 mt-1">
                {pageList.length === 0
                  ? 'No data yet — add the JS SDK to your site first'
                  : `${pageList.length} page${pageList.length !== 1 ? 's' : ''} tracked`}
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {/* Click map + Scroll depth — SIDE BY SIDE */}
              <div className="grid grid-cols-[3fr_2fr] gap-4 items-start">

                {/* Click Map */}
                <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-gray-700">Click Map</p>
                    <span className="text-[10px] text-gray-400 font-mono">{pagePath}</span>
                  </div>
                  <ClickGrid
                    cells={clickData?.cells ?? []}
                    total={clickData?.total_clicks ?? 0}
                  />
                </div>

                {/* Scroll Depth */}
                <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
                  <p className="text-xs font-semibold text-gray-700 mb-1">Scroll Depth</p>
                  <p className="text-[10px] text-gray-400 mb-2">
                    % of sessions reaching each depth
                  </p>
                  <ScrollChart
                    buckets={scrollData?.buckets ?? []}
                    total={scrollData?.total_sessions ?? 0}
                  />
                </div>
              </div>

              {/* Setup snippet — compact */}
              <div className="bg-gray-900 rounded-2xl border border-gray-700 px-4 py-3">
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-1.5">
                  Enable heatmap tracking
                </p>
                <pre className="text-[11px] text-gray-300 font-mono leading-relaxed overflow-x-auto">{`Analytics.init('YOUR_API_KEY', { host: 'https://your-host.com', heatmaps: true });`}</pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

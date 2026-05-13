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

// ── Click grid ────────────────────────────────────────────────────────────────

function intensityColor(v: number): string {
  if (v === 0)   return 'bg-blue-50';
  if (v < 15)    return 'bg-blue-100';
  if (v < 30)    return 'bg-cyan-200';
  if (v < 45)    return 'bg-green-300';
  if (v < 60)    return 'bg-yellow-300';
  if (v < 75)    return 'bg-orange-400';
  if (v < 90)    return 'bg-red-500';
  return 'bg-red-700';
}

interface GridCell { row: number; col: number; intensity: number; count: number }

function ClickGrid({ cells, total }: { cells: GridCell[]; total: number }) {
  // Build 10×10 matrix
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
      <div className="flex flex-col items-center justify-center h-48 text-gray-400 text-sm">
        <p className="text-3xl mb-2">🖱️</p>
        No click data yet for this page.
      </div>
    );
  }

  return (
    <div>
      <div className="grid gap-0.5" style={{ gridTemplateColumns: 'repeat(10, 1fr)' }}>
        {matrix.flatMap((row, ri) =>
          row.map((intensity, ci) => (
            <div
              key={`${ri}-${ci}`}
              title={`(${ci * 10}–${ci * 10 + 10}% x, ${ri * 10}–${ri * 10 + 10}% y) · ${counts[ri][ci]} clicks`}
              className={`aspect-square rounded-sm transition-colors ${intensityColor(intensity)}`}
            />
          ))
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-2 mt-3 justify-center">
        <span className="text-xs text-gray-400">Cold</span>
        {[0, 20, 40, 60, 80, 100].map(v => (
          <div key={v} className={`w-5 h-3 rounded-sm ${intensityColor(v)}`} />
        ))}
        <span className="text-xs text-gray-400">Hot</span>
        <span className="ml-3 text-xs text-gray-400">{total.toLocaleString()} total clicks</span>
      </div>
    </div>
  );
}

// ── Scroll depth ──────────────────────────────────────────────────────────────

interface ScrollBucket { depth: number; sessions: number; pct: number }

function ScrollChart({ buckets, total }: { buckets: ScrollBucket[]; total: number }) {
  if (total === 0 || buckets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-gray-400 text-sm">
        <p className="text-2xl mb-2">📜</p>
        No scroll data yet.
      </div>
    );
  }

  const map = new Map(buckets.map(b => [b.depth, b]));

  return (
    <div className="space-y-1.5">
      {[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map(depth => {
        const b     = map.get(depth);
        const pct   = b?.pct ?? 0;
        const color = pct > 70 ? 'bg-green-500' : pct > 40 ? 'bg-indigo-400' : pct > 20 ? 'bg-indigo-300' : 'bg-gray-200';
        return (
          <div key={depth} className="flex items-center gap-2">
            <span className="text-xs text-gray-400 w-8 text-right shrink-0">{depth}%</span>
            <div className="flex-1 h-4 bg-gray-50 rounded-md overflow-hidden">
              <div className={`h-full rounded-md ${color} transition-all`} style={{ width: `${pct}%` }} />
            </div>
            <span className="text-xs text-gray-500 w-10 tabular-nums">{pct}%</span>
          </div>
        );
      })}
      <p className="text-xs text-gray-400 text-right mt-1">{total} sessions sampled</p>
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
      <div className="text-sm text-gray-400 text-center py-6">
        No pages tracked yet.<br />
        <span className="text-xs">Add the JS SDK snippet to start capturing clicks.</span>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      {pages.map(p => {
        const path = (() => { try { return new URL(p.page_url).pathname || p.page_url; } catch { return p.page_url; } })();
        return (
          <button
            key={p.page_url}
            onClick={() => onSelect(p.page_url)}
            className={`w-full text-left px-3 py-2.5 rounded-xl text-sm transition-colors ${
              selected === p.page_url
                ? 'bg-indigo-50 text-indigo-700 font-medium'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <p className="font-mono text-xs truncate">{path}</p>
            <p className="text-xs text-gray-400 mt-0.5">
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

  const pageList = pages ?? [];

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Heatmaps</h1>
            <p className="mt-0.5 text-sm text-gray-500">
              Click maps · scroll depth · rage-click detection
            </p>
          </div>
          <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
            {[7, 30, 90].map(d => (
              <button key={d} onClick={() => setDays(d)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  days === d ? 'bg-white text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}>
                {d}d
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-[240px_1fr] gap-6 items-start">

          {/* Page list */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Pages</p>
            <PageList pages={pageList} selected={selectedUrl} onSelect={setSelectedUrl} />
          </div>

          {/* Main panel */}
          <div className="space-y-6">
            {!selectedUrl ? (
              <div className="bg-white rounded-2xl border border-gray-100 shadow-sm flex flex-col
                              items-center justify-center py-24 text-gray-400">
                <p className="text-4xl mb-3">👈</p>
                <p className="text-sm font-medium text-gray-600">Select a page to view its heatmap</p>
                <p className="text-xs text-gray-400 mt-1">
                  {pageList.length === 0
                    ? 'No data yet — add the JS SDK to your site first'
                    : `${pageList.length} page${pageList.length !== 1 ? 's' : ''} tracked`}
                </p>
              </div>
            ) : (
              <>
                {/* Click heatmap */}
                <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-sm font-semibold text-gray-700">Click Map</h2>
                    <span className="text-xs text-gray-400 font-mono truncate max-w-xs">
                      {(() => { try { return new URL(selectedUrl).pathname; } catch { return selectedUrl; } })()}
                    </span>
                  </div>
                  <ClickGrid
                    cells={clickData?.cells ?? []}
                    total={clickData?.total_clicks ?? 0}
                  />
                </div>

                {/* Scroll depth */}
                <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
                  <h2 className="text-sm font-semibold text-gray-700 mb-4">Scroll Depth</h2>
                  <ScrollChart
                    buckets={scrollData?.buckets ?? []}
                    total={scrollData?.total_sessions ?? 0}
                  />
                </div>
              </>
            )}

            {/* Setup snippet */}
            <div className="bg-gray-900 rounded-2xl border border-gray-700 p-5">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
                Enable heatmap tracking
              </p>
              <pre className="text-xs text-gray-100 font-mono leading-relaxed overflow-x-auto">{`// analytics.js auto-tracks clicks + scroll when heatmaps: true
Analytics.init('YOUR_API_KEY', {
  host:     'https://your-host.com',
  heatmaps: true,   // ← add this
});`}</pre>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

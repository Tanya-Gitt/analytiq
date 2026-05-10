'use client';

import type { FunnelStep } from '@/lib/api';

interface Props {
  data: FunnelStep[];
  filteredBy?: string; // event_type filter label, if active
}

const STEP_LABELS: Record<string, string> = {
  page_view:           'Page View',
  product_viewed:      'Product Viewed',
  add_to_cart:         'Add to Cart',
  checkout_started:    'Checkout Started',
  purchase_completed:  'Purchase Completed',
};

const COLORS = ['#6366f1', '#7c3aed', '#8b5cf6', '#a78bfa', '#c4b5fd'];

export default function FunnelChart({ data, filteredBy }: Props) {
  const nonEmpty = data.filter(s => s.users > 0);

  if (!nonEmpty.length) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400 text-center">
        No funnel data yet — track page_view, product_viewed, add_to_cart,<br />
        checkout_started, purchase_completed events to see the funnel.
      </div>
    );
  }

  // Bar widths are relative to the first non-zero step (top of funnel).
  // Using the first step as the reference makes each bar show
  // "what % of funnel-top users reached this step."
  const topUsers = nonEmpty[0].users;

  return (
    <div className="space-y-2 py-2">
      {/* Context label when an event filter is active */}
      {filteredBy && (
        <p className="text-xs text-indigo-600 bg-indigo-50 rounded-md px-2 py-1 mb-3">
          Showing funnel for users who did <strong>{filteredBy}</strong>
        </p>
      )}

      {data.map((step, i) => {
        // Bar width = step users / top-of-funnel users (not relative to max of all steps)
        const pct = topUsers > 0 ? (step.users / topUsers) * 100 : 0;

        // Step-over-step drop from the PREVIOUS step
        const prevUsers = i > 0 ? data[i - 1].users : null;
        const dropPct = prevUsers != null && prevUsers > 0 && step.users > 0
          ? ((prevUsers - step.users) / prevUsers) * 100
          : null;

        // Conversion from TOP of funnel to this step
        const fromTopPct = topUsers > 0 && i > 0
          ? (step.users / topUsers) * 100
          : null;

        return (
          <div key={step.step}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-600">
                {STEP_LABELS[step.step] ?? step.step}
              </span>
              <div className="flex items-center gap-3">
                {/* Step-over-step drop */}
                {dropPct !== null && (
                  <span className="text-xs text-red-400 tabular-nums">
                    ↓ {dropPct.toFixed(0)}%
                  </span>
                )}
                {/* % retained from top */}
                {fromTopPct !== null && (
                  <span className="text-xs text-gray-400 tabular-nums">
                    {fromTopPct.toFixed(0)}% of top
                  </span>
                )}
                <span className="text-xs font-semibold text-gray-800 w-12 text-right tabular-nums">
                  {step.users > 0 ? step.users.toLocaleString() : '—'}
                </span>
              </div>
            </div>
            <div className="h-6 bg-gray-100 rounded-md overflow-hidden">
              <div
                className="h-full rounded-md transition-all duration-500"
                style={{
                  width: step.users > 0 ? `${pct}%` : '0%',
                  backgroundColor: COLORS[i % COLORS.length],
                  minWidth: step.users > 0 ? 4 : 0,
                }}
              />
            </div>
          </div>
        );
      })}

      {/* Overall conversion: first non-zero step → last non-zero step */}
      {nonEmpty.length >= 2 && (
        <div className="mt-3 pt-3 border-t border-gray-100 flex justify-between text-xs text-gray-500">
          <span>Overall conversion</span>
          <span className="font-semibold text-indigo-600">
            {((nonEmpty[nonEmpty.length - 1].users / nonEmpty[0].users) * 100).toFixed(1)}%
          </span>
        </div>
      )}
    </div>
  );
}

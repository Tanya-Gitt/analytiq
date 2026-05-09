'use client';

import type { FunnelStep } from '@/lib/api';

interface Props { data: FunnelStep[] }

const STEP_LABELS: Record<string, string> = {
  page_view:           'Page View',
  product_viewed:      'Product Viewed',
  add_to_cart:         'Add to Cart',
  checkout_started:    'Checkout Started',
  purchase_completed:  'Purchase Completed',
};

const COLORS = ['#6366f1', '#7c3aed', '#8b5cf6', '#a78bfa', '#c4b5fd'];

export default function FunnelChart({ data }: Props) {
  const nonEmpty = data.filter(s => s.users > 0);

  if (!nonEmpty.length) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400">
        No funnel data yet — track page_view, product_viewed, add_to_cart,<br />
        checkout_started, purchase_completed events to see the funnel.
      </div>
    );
  }

  const maxUsers = Math.max(...data.map(s => s.users), 1);

  return (
    <div className="space-y-2 py-2">
      {data.map((step, i) => {
        const pct = maxUsers > 0 ? (step.users / maxUsers) * 100 : 0;
        const dropPct = i > 0 && data[i - 1].users > 0
          ? ((data[i - 1].users - step.users) / data[i - 1].users * 100)
          : null;

        return (
          <div key={step.step}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-600">
                {STEP_LABELS[step.step] ?? step.step}
              </span>
              <div className="flex items-center gap-2">
                {dropPct !== null && step.users > 0 && (
                  <span className="text-xs text-red-400">
                    ↓ {dropPct.toFixed(0)}%
                  </span>
                )}
                <span className="text-xs font-semibold text-gray-800 w-12 text-right">
                  {step.users.toLocaleString()}
                </span>
              </div>
            </div>
            <div className="h-6 bg-gray-100 rounded-md overflow-hidden">
              <div
                className="h-full rounded-md transition-all duration-500"
                style={{
                  width: `${pct}%`,
                  backgroundColor: COLORS[i % COLORS.length],
                  minWidth: step.users > 0 ? 4 : 0,
                }}
              />
            </div>
          </div>
        );
      })}

      {/* Conversion rate summary */}
      {data[0]?.users > 0 && data[data.length - 1]?.users > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-100 flex justify-between text-xs text-gray-500">
          <span>Overall conversion</span>
          <span className="font-semibold text-indigo-600">
            {((data[data.length - 1].users / data[0].users) * 100).toFixed(1)}%
          </span>
        </div>
      )}
    </div>
  );
}

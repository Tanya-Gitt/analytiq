'use client';

import type { RetentionCohort } from '@/lib/api';

interface Props {
  cohorts: RetentionCohort[];
  weeks:   number;
}

// ── Colour scale: 0%=white → 100%=indigo-700 ─────────────────────────────────

function retentionColor(pct: number): string {
  // Clamp to [0, 1]
  const p = Math.max(0, Math.min(1, pct));
  if (p === 0) return 'bg-gray-50 text-gray-400';
  if (p < 0.1)  return 'bg-indigo-50 text-indigo-400';
  if (p < 0.2)  return 'bg-indigo-100 text-indigo-500';
  if (p < 0.35) return 'bg-indigo-200 text-indigo-700';
  if (p < 0.5)  return 'bg-indigo-300 text-indigo-800';
  if (p < 0.65) return 'bg-indigo-400 text-white';
  if (p < 0.8)  return 'bg-indigo-500 text-white';
  return 'bg-indigo-700 text-white';
}

function fmtWeek(iso: string) {
  // iso = "YYYY-MM-DD" (Monday of cohort week)
  const d = new Date(iso + 'T00:00:00Z');
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day:   'numeric',
    timeZone: 'UTC',
  });
}

export default function RetentionCohortChart({ cohorts, weeks }: Props) {
  if (!cohorts.length) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400 text-center">
        No retention data yet — track events with a <code>user_id</code> to see cohorts.
      </div>
    );
  }

  // Build a set of all week offsets present (0…weeks-1)
  const maxWk = weeks - 1;
  const colHeaders = Array.from({ length: Math.min(weeks, maxWk + 1) }, (_, i) => i);

  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse min-w-full">
        <thead>
          <tr>
            <th className="text-left px-2 py-1.5 text-gray-500 font-medium whitespace-nowrap">
              Cohort
            </th>
            <th className="px-2 py-1.5 text-gray-500 font-medium text-right whitespace-nowrap">
              Users
            </th>
            {colHeaders.map(w => (
              <th
                key={w}
                className="px-1 py-1.5 text-gray-400 font-medium text-center min-w-[36px]"
              >
                Wk {w}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cohorts.map(cohort => {
            const retMap: Record<number, number> = {};
            for (const w of cohort.weeks) {
              retMap[w.week_number] = w.retained;
            }

            return (
              <tr key={cohort.cohort_week} className="hover:bg-gray-50 transition-colors">
                {/* Cohort week label */}
                <td className="px-2 py-1 text-gray-700 font-medium whitespace-nowrap">
                  {fmtWeek(cohort.cohort_week)}
                </td>

                {/* Cohort size */}
                <td className="px-2 py-1 text-gray-500 text-right tabular-nums">
                  {cohort.cohort_size.toLocaleString()}
                </td>

                {/* Retention cells */}
                {colHeaders.map(wk => {
                  const retained = retMap[wk];
                  const pct = retained != null && cohort.cohort_size > 0
                    ? retained / cohort.cohort_size
                    : null;
                  const label = pct != null
                    ? `${(pct * 100).toFixed(0)}%`
                    : '—';

                  return (
                    <td key={wk} className="px-0.5 py-0.5">
                      <div
                        className={`flex items-center justify-center rounded text-center tabular-nums font-medium h-7 min-w-[34px] ${
                          pct != null ? retentionColor(pct) : 'text-gray-300'
                        }`}
                        title={pct != null
                          ? `${retained?.toLocaleString()} / ${cohort.cohort_size.toLocaleString()} users (${(pct * 100).toFixed(1)}%)`
                          : 'No data'}
                      >
                        {label}
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Legend */}
      <div className="flex items-center gap-2 mt-3 pt-2 border-t border-gray-100">
        <span className="text-xs text-gray-400 mr-1">Retention:</span>
        {[
          { cls: 'bg-gray-50',     label: '0%' },
          { cls: 'bg-indigo-100',  label: '10%' },
          { cls: 'bg-indigo-200',  label: '20%' },
          { cls: 'bg-indigo-300',  label: '35%' },
          { cls: 'bg-indigo-400',  label: '50%' },
          { cls: 'bg-indigo-500',  label: '65%' },
          { cls: 'bg-indigo-700',  label: '80%+' },
        ].map(({ cls, label }) => (
          <div key={label} className="flex items-center gap-1">
            <div className={`w-4 h-4 rounded ${cls} border border-gray-200`} />
            <span className="text-xs text-gray-400">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

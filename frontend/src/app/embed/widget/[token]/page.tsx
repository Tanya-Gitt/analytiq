'use client';

import { use, useEffect, useState } from 'react';

interface WidgetData {
  widget_type: string;
  config: Record<string, unknown>;
  data: Record<string, unknown>;
}

export default function EmbedWidgetPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [data, setData] = useState<WidgetData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/embed/public/${token}`)
      .then(r => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch(e => setError(e.message));
  }, [token]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen text-sm text-red-600">
        {error === '404' ? 'Invalid or expired embed token' : `Error: ${error}`}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center h-screen text-sm text-gray-400">
        Loading…
      </div>
    );
  }

  return (
    <div className="p-4 font-sans">
      <WidgetRenderer data={data} />
    </div>
  );
}

function WidgetRenderer({ data }: { data: WidgetData }) {
  const { widget_type, data: wd } = data;

  if (widget_type === 'events_chart') {
    const series = (wd.series as { date: string; events: number }[]) || [];
    const max = Math.max(...series.map(s => s.events), 1);
    return (
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Events Over Time</h3>
        <div className="flex items-end gap-1 h-32">
          {series.map((pt, i) => (
            <div key={i} className="flex-1 flex flex-col items-center" title={`${pt.date}: ${pt.events}`}>
              <div
                className="w-full bg-blue-400 rounded-t"
                style={{ height: `${Math.max(4, Math.round((pt.events / max) * 120))}px` }}
              />
              <span className="text-xs text-gray-400 mt-1 rotate-45 origin-left hidden sm:block">{pt.date.slice(5)}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (widget_type === 'top_events') {
    const events = (wd.events as { name: string; count: number }[]) || [];
    const max = Math.max(...events.map(e => e.count), 1);
    return (
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Top Events</h3>
        <div className="space-y-2">
          {events.map((ev, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className="font-mono text-xs w-32 truncate text-gray-700">{ev.name}</span>
              <div className="flex-1 bg-gray-100 rounded h-2">
                <div className="bg-blue-500 h-2 rounded" style={{ width: `${Math.round((ev.count / max) * 100)}%` }} />
              </div>
              <span className="text-xs text-gray-500">{ev.count}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (widget_type === 'funnel') {
    const funnel = (wd.funnel as { step: string; users: number }[]) || [];
    const max = funnel[0]?.users || 1;
    return (
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Funnel</h3>
        <div className="space-y-2">
          {funnel.map((step, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className="w-4 text-xs text-gray-400">{i + 1}</span>
              <span className="font-mono text-xs w-28 truncate text-gray-700">{step.step}</span>
              <div className="flex-1 bg-gray-100 rounded h-4">
                <div
                  className="bg-indigo-500 h-4 rounded text-xs text-white flex items-center justify-end pr-1"
                  style={{ width: `${Math.round((step.users / max) * 100)}%` }}
                >
                  {step.users}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return <pre className="text-xs text-gray-500">{JSON.stringify(data, null, 2)}</pre>;
}

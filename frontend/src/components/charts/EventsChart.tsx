'use client';

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import type { EventsTimelinePoint, Annotation } from '@/lib/api';

interface Props {
  data: EventsTimelinePoint[];
  annotations?: Annotation[];
}

export default function EventsChart({ data, annotations = [] }: Props) {
  if (!data.length) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400">
        No events data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={d => d.slice(5)}
        />
        <YAxis
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
          width={40}
        />
        <Tooltip
          formatter={(v: number) => [v.toLocaleString(), 'Events']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
        />
        {annotations.map(ann => (
          <ReferenceLine
            key={ann.id}
            x={ann.date}
            stroke={ann.color}
            strokeWidth={2}
            strokeDasharray="4 2"
            label={{
              value: ann.label,
              position: 'insideTopRight',
              fontSize: 10,
              fill: ann.color,
            }}
          />
        ))}
        <Bar dataKey="count" fill="#6366f1" radius={[3, 3, 0, 0]} maxBarSize={40} />
      </BarChart>
    </ResponsiveContainer>
  );
}

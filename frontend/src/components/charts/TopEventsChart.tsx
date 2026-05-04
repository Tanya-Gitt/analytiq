'use client';

import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import type { TopEvent } from '@/lib/api';

const COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe'];

interface Props {
  data: TopEvent[];
}

export default function TopEventsChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400">
        No events yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 20, bottom: 0, left: 90 }}
      >
        <XAxis
          type="number"
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          type="category"
          dataKey="event_name"
          tick={{ fontSize: 12, fill: '#374151' }}
          tickLine={false}
          axisLine={false}
          width={85}
        />
        <Tooltip
          formatter={(v: number) => [v.toLocaleString(), 'Count']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
        />
        <Bar dataKey="count" radius={[0, 4, 4, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

'use client';

import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import type { TopChannel } from '@/lib/api';

const COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe'];

interface Props {
  data: TopChannel[];
}

function fmt(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

export default function TopChannelsChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400">
        No channel data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 20, bottom: 0, left: 60 }}
      >
        <XAxis
          type="number"
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={fmt}
        />
        <YAxis
          type="category"
          dataKey="channel"
          tick={{ fontSize: 12, fill: '#374151' }}
          tickLine={false}
          axisLine={false}
          width={55}
        />
        <Tooltip
          formatter={(v: number) => [fmt(v), 'Revenue']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
        />
        <Bar dataKey="revenue" radius={[0, 4, 4, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

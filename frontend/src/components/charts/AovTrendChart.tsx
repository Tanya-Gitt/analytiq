'use client';

import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import type { AovTrendPoint } from '@/lib/api';

interface Props { data: AovTrendPoint[] }

function fmt(v: number) {
  return `$${v.toFixed(0)}`;
}

export default function AovTrendChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400">
        No AOV data yet
      </div>
    );
  }

  const avg = data.reduce((s, d) => s + d.aov, 0) / data.length;

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <XAxis
          dataKey="date"
          tickFormatter={d => d.slice(5)}
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          axisLine={false}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tickFormatter={fmt}
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          axisLine={false}
          tickLine={false}
          width={42}
        />
        <Tooltip
          formatter={(v: number) => [fmt(v), 'Avg Order Value']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
        />
        <ReferenceLine
          y={avg}
          stroke="#e5e7eb"
          strokeDasharray="4 4"
          label={{ value: `avg ${fmt(avg)}`, position: 'insideTopRight', fontSize: 10, fill: '#9ca3af' }}
        />
        <Line
          type="monotone"
          dataKey="aov"
          stroke="#8b5cf6"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: '#8b5cf6' }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

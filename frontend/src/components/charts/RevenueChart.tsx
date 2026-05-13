'use client';

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import type { RevenueTrendPoint, Annotation } from '@/lib/api';

interface Props {
  data: RevenueTrendPoint[];
  annotations?: Annotation[];
}

function fmt(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

export default function RevenueChart({ data, annotations = [] }: Props) {
  if (!data.length) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400">
        No revenue data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0}   />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
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
          tickFormatter={fmt}
          width={52}
        />
        <Tooltip
          formatter={(v: number) => [fmt(v), 'Revenue']}
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
        <Area
          type="monotone"
          dataKey="revenue"
          stroke="#6366f1"
          strokeWidth={2}
          fill="url(#rev)"
          dot={false}
          activeDot={{ r: 4, fill: '#4f46e5' }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

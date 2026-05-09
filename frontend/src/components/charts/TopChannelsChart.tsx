'use client';

import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import type { TopChannel } from '@/lib/api';

// Perceptually distinct colors — each channel reads at a glance
const COLORS: Record<string, string> = {
  organic:     '#6366f1', // indigo
  paid_search: '#f59e0b', // amber
  email:       '#10b981', // emerald
  social:      '#ef4444', // red
  referral:    '#3b82f6', // blue
  direct:      '#8b5cf6', // violet
  paid_ads:    '#f97316', // orange
};
const FALLBACK_COLORS = ['#14b8a6', '#ec4899', '#84cc16', '#06b6d4', '#a855f7'];

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
      <PieChart>
        <Pie
          data={data}
          dataKey="revenue"
          nameKey="channel"
          cx="50%"
          cy="50%"
          innerRadius={52}
          outerRadius={80}
          paddingAngle={3}
        >
          {data.map((entry, i) => (
            <Cell key={i} fill={COLORS[entry.channel] ?? FALLBACK_COLORS[i % FALLBACK_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          formatter={(v: number) => [fmt(v), 'Revenue']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={(value) => (
            <span style={{ fontSize: 12, color: '#374151' }}>{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

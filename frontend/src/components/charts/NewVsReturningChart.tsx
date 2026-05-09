'use client';

import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import type { NewVsReturningPoint } from '@/lib/api';

interface Props { data: NewVsReturningPoint[] }

export default function NewVsReturningChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400">
        No user data yet — identify users with Analytics.identify() to see this chart.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="colorNew" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="colorRet" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#a78bfa" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#a78bfa" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="date"
          tickFormatter={d => d.slice(5)}
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          axisLine={false}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          axisLine={false}
          tickLine={false}
          width={28}
        />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={value => (
            <span style={{ fontSize: 12, color: '#374151' }}>
              {value === 'new_users' ? 'New' : 'Returning'}
            </span>
          )}
        />
        <Area
          type="monotone"
          dataKey="new_users"
          name="new_users"
          stroke="#6366f1"
          strokeWidth={2}
          fill="url(#colorNew)"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="returning_users"
          name="returning_users"
          stroke="#a78bfa"
          strokeWidth={2}
          fill="url(#colorRet)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

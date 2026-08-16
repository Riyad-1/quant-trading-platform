'use client'

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

interface EquityPoint {
  date: string
  strategy?: number
  benchmark?: number
  equity?: number
  risk?: number
}

export default function Chart({ data, mode = 'equity' }: { data: EquityPoint[]; mode?: 'equity' | 'risk' }) {
  const keys = mode === 'risk' ? ['risk'] : data.some((point) => point.benchmark !== undefined) ? ['strategy', 'benchmark'] : ['equity']
  const colors: Record<string, string> = { strategy: '#22d3ee', benchmark: '#818cf8', equity: '#34d399', risk: '#f59e0b' }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            {keys.map((key) => (
              <linearGradient key={key} id={`fill-${key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={colors[key]} stopOpacity={0.28} />
                <stop offset="95%" stopColor={colors[key]} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke="rgba(148,163,184,0.09)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={38} />
          <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false} width={52} tickFormatter={(value) => mode === 'risk' ? `${value}` : `$${Math.round(Number(value) / 1000)}k`} />
          <Tooltip contentStyle={{ background: '#0b1220', border: '1px solid rgba(148,163,184,.16)', borderRadius: 12, fontSize: 12 }} formatter={(value: number) => mode === 'risk' ? value.toFixed(1) : `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
          {keys.map((key) => <Area key={key} type="monotone" dataKey={key} stroke={colors[key]} fill={`url(#fill-${key})`} strokeWidth={2} dot={false} />)}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

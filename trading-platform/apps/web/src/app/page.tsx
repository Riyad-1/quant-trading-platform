'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { Activity, ArrowRight, BarChart3, BrainCircuit, CandlestickChart, Database, Newspaper, Radio, ShieldCheck, WalletCards } from 'lucide-react'
import MetricCard from '@/components/MetricCard'
import PageHeader from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { api, apiErrorMessage, HealthResponse, MLStatus, PaperSummary, RegimeResponse } from '@/lib/api'
import { formatCurrency, titleCase } from '@/lib/utils'

const modules = [
  { href: '/scanner', title: 'Opportunity scanner', detail: 'Rank the recovered mock universe by momentum, breakout and relative strength.', icon: Radio, tone: 'Mock data' },
  { href: '/backtest', title: 'SPY backtesting', detail: 'Run a next-open, cost-aware trend test against SPY buy-and-hold.', icon: BarChart3, tone: 'Real data' },
  { href: '/regime', title: 'Market regime', detail: 'Review risk, breadth and strategy compatibility from the regime engine.', icon: Activity, tone: 'Simulation' },
  { href: '/news', title: 'News catalysts', detail: 'Ingest mock articles and process events with the recovered rule engine.', icon: Newspaper, tone: 'Rule based' },
  { href: '/ml', title: 'ML laboratory', detail: 'Inspect model readiness, supported estimators and registry state.', icon: BrainCircuit, tone: 'Registry' },
  { href: '/paper', title: 'Paper execution', detail: 'Submit simulated orders through position and concentration risk checks.', icon: CandlestickChart, tone: 'In memory' },
  { href: '/portfolio', title: 'Portfolios', detail: 'Create persistent database portfolios and inspect positions and equity.', icon: WalletCards, tone: 'PostgreSQL' },
]

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [regime, setRegime] = useState<RegimeResponse | null>(null)
  const [ml, setMl] = useState<MLStatus | null>(null)
  const [paper, setPaper] = useState<PaperSummary | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([
      api.get<HealthResponse>('/api/v1/health'),
      api.get<RegimeResponse>('/api/v1/regime/current'),
      api.get<MLStatus>('/api/v1/ml/status'),
      api.get<PaperSummary>('/api/v1/paper/summary'),
    ]).then(([healthResponse, regimeResponse, mlResponse, paperResponse]) => {
      setHealth(healthResponse.data)
      setRegime(regimeResponse.data)
      setMl(mlResponse.data)
      setPaper(paperResponse.data)
    }).catch((requestError) => setError(apiErrorMessage(requestError)))
  }, [])

  return (
    <main>
      <PageHeader eyebrow="Command centre" title="Quant research, without the black box." description="A working surface over the recovered scanner, regime, news, ML, backtesting, paper execution and portfolio services. Every module identifies whether its data is real, simulated or awaiting training." actions={<Badge tone={health?.status === 'healthy' ? 'positive' : error ? 'negative' : 'warning'}>{health?.status === 'healthy' ? 'Systems online' : error ? 'API offline' : 'Connecting'}</Badge>} />

      <section className="section-grid">
        <MetricCard label="Database" value={health?.database ? titleCase(health.database) : 'Checking'} detail="PostgreSQL + TimescaleDB" icon={Database} tone={health?.database === 'connected' ? 'positive' : 'default'} />
        <MetricCard label="Market regime" value={regime ? titleCase(regime.regime) : 'Loading'} detail={regime ? `${Math.round(regime.confidence * 100)}% confidence · simulated input` : 'Regime detector'} icon={Activity} />
        <MetricCard label="ML registry" value={ml ? `${ml.registered_models} models` : 'Loading'} detail={ml ? titleCase(ml.status) : 'Inspecting registry'} icon={BrainCircuit} />
        <MetricCard label="Paper equity" value={paper ? formatCurrency(paper.total_value, true) : 'Loading'} detail={paper ? `${paper.num_positions} open positions · in memory` : 'Execution engine'} icon={ShieldCheck} tone={paper && paper.total_pnl >= 0 ? 'positive' : 'default'} />
      </section>

      {error && <div className="mt-5 rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">The dashboard could not reach the refreshed API: {error}. Rebuild the API container after these changes.</div>}

      <section className="mt-10">
        <div className="mb-4 flex items-end justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Workspace</p><h2 className="mt-1 text-xl font-semibold text-white">Research modules</h2></div><a href="http://localhost:8000/docs" target="_blank" className="text-xs text-primary hover:text-cyan-200">Open API docs ↗</a></div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {modules.map(({ href, title, detail, icon: Icon, tone }) => (
            <Link key={href} href={href} className="group">
              <Card className="h-full transition duration-300 hover:-translate-y-0.5 hover:border-primary/25">
                <CardHeader className="flex-row items-start justify-between"><span className="rounded-xl border border-white/10 bg-white/5 p-3 text-cyan-200"><Icon size={20} /></span><Badge tone={tone === 'Real data' ? 'positive' : 'neutral'}>{tone}</Badge></CardHeader>
                <CardContent><CardTitle>{title}</CardTitle><CardDescription className="mt-2 leading-6">{detail}</CardDescription><span className="mt-5 flex items-center gap-2 text-xs font-medium text-primary">Open module <ArrowRight size={14} className="transition group-hover:translate-x-1" /></span></CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>
    </main>
  )
}

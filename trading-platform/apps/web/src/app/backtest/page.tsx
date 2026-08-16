'use client'

import { FormEvent, useState } from 'react'
import { BarChart3, CalendarRange, Play, ShieldCheck, TrendingDown, Wallet } from 'lucide-react'
import Chart from '@/components/Chart'
import MetricCard from '@/components/MetricCard'
import PageHeader from '@/components/PageHeader'
import { ErrorState, LoadingState } from '@/components/PanelState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api, apiErrorMessage, BacktestResult } from '@/lib/api'
import { formatCurrency, formatPercent } from '@/lib/utils'

const latestCompletedDate = () => {
  const value = new Date(); value.setDate(value.getDate() - 1); return value.toISOString().slice(0, 10)
}

export default function BacktestPage() {
  const [startDate, setStartDate] = useState('2015-01-01')
  const [endDate, setEndDate] = useState(latestCompletedDate)
  const [capital, setCapital] = useState(100000)
  const [sma, setSma] = useState(200)
  const [commission, setCommission] = useState(5)
  const [slippage, setSlippage] = useState(5)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function runBacktest(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError('')
    try {
      const response = await api.post<BacktestResult>('/api/v1/backtest/run', null, { params: { start_date: startDate, end_date: endDate, initial_capital: capital, sma_period: sma, commission_bps: commission, slippage_bps: slippage } })
      setResult(response.data)
    } catch (requestError) { setResult(null); setError(apiErrorMessage(requestError)) } finally { setLoading(false) }
  }

  return (
    <main>
      <PageHeader eyebrow="Historical simulation" title="SPY trend backtest" description="A transparent long-or-cash test against SPY buy-and-hold. Signals are formed after the close, executed at the next open, and both portfolios pay identical entry and exit costs." actions={<Badge tone="positive">Real adjusted SPY data</Badge>} />

      <Card className="mt-6"><CardContent className="pt-5"><form onSubmit={runBacktest} className="grid items-end gap-4 md:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_120px_110px_110px_auto]"><label><span className="label">Start</span><input className="field" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></label><label><span className="label">End</span><input className="field" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></label><label><span className="label">Capital</span><input className="field" type="number" min={1000} value={capital} onChange={(e) => setCapital(Number(e.target.value))} /></label><label><span className="label">SMA days</span><input className="field" type="number" min={50} max={300} value={sma} onChange={(e) => setSma(Number(e.target.value))} /></label><label><span className="label">Fee bps</span><input className="field" type="number" min={0} value={commission} onChange={(e) => setCommission(Number(e.target.value))} /></label><label><span className="label">Slip bps</span><input className="field" type="number" min={0} value={slippage} onChange={(e) => setSlippage(Number(e.target.value))} /></label><Button disabled={loading} type="submit"><Play size={15} />{loading ? 'Running…' : 'Run test'}</Button></form></CardContent></Card>

      {loading && <Card className="mt-6"><LoadingState label="Downloading adjusted SPY history and simulating next-open execution" /></Card>}
      {error && <Card className="mt-6"><ErrorState message={error} /></Card>}

      {result && <>
        <section className="section-grid">
          <MetricCard label="Strategy ROI" value={formatPercent(result.strategy.roi)} detail={`${result.start_date} → ${result.end_date}`} icon={Wallet} tone={result.strategy.roi >= 0 ? 'positive' : 'negative'} />
          <MetricCard label="SPY ROI" value={formatPercent(result.benchmark.roi)} detail="Cost-adjusted buy and hold" icon={BarChart3} tone={result.benchmark.roi >= 0 ? 'positive' : 'negative'} />
          <MetricCard label="Excess ROI" value={formatPercent(result.excess_roi)} detail="Strategy minus benchmark" icon={TrendingDown} tone={result.excess_roi >= 0 ? 'positive' : 'negative'} />
          <MetricCard label="Market exposure" value={formatPercent(result.market_exposure)} detail={`${result.entries} entries · ${result.exits} exits`} icon={ShieldCheck} />
        </section>

        <Card className="mt-6"><CardHeader className="flex-row items-start justify-between"><div><CardTitle>Equity curve</CardTitle><CardDescription>{result.execution} · {result.data_source}</CardDescription></div><Badge>{result.strategy_name}</Badge></CardHeader><CardContent><Chart data={result.equity_curve} /></CardContent></Card>

        <div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_.6fr]">
          <Card className="overflow-hidden"><CardHeader><CardTitle>Performance comparison</CardTitle><CardDescription>Returns are cumulative; volatility and drawdown are annualized and peak-relative respectively.</CardDescription></CardHeader><Table><TableHeader><TableRow><TableHead>Portfolio</TableHead><TableHead>Final equity</TableHead><TableHead>ROI</TableHead><TableHead>CAGR</TableHead><TableHead>Max drawdown</TableHead><TableHead>Sharpe</TableHead></TableRow></TableHeader><TableBody>{[['Trend strategy', result.strategy], ['SPY buy & hold', result.benchmark]].map(([name, metrics]) => { const item = metrics as BacktestResult['strategy']; return <TableRow key={name as string}><TableCell className="font-medium text-white">{name as string}</TableCell><TableCell className="font-mono">{formatCurrency(item.final_equity)}</TableCell><TableCell className="font-mono">{formatPercent(item.roi)}</TableCell><TableCell className="font-mono">{formatPercent(item.cagr)}</TableCell><TableCell className="font-mono text-rose-300">{formatPercent(item.max_drawdown)}</TableCell><TableCell className="font-mono">{item.sharpe_zero_rf.toFixed(2)}</TableCell></TableRow>})}</TableBody></Table></Card>
          <Card><CardHeader><CardTitle>Assumptions</CardTitle><CardDescription>Keep these limits visible when interpreting results.</CardDescription></CardHeader><CardContent><ul className="space-y-3 text-sm text-muted-foreground">{result.limitations.map((limit) => <li key={limit} className="flex gap-3"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />{limit}</li>)}</ul><div className="mt-5 rounded-xl border border-amber-400/15 bg-amber-400/5 p-4 text-xs leading-5 text-amber-200/80"><CalendarRange className="mb-2" size={17} />Changing the SMA after viewing results creates selection bias. Keep a separate out-of-sample period.</div></CardContent></Card>
        </div>
      </>}

      {!result && !loading && !error && <Card className="mt-6"><CardContent className="flex min-h-56 flex-col items-center justify-center text-center"><BarChart3 className="text-primary" size={28} /><p className="mt-4 font-medium text-white">Ready to test</p><p className="mt-2 max-w-lg text-sm leading-6 text-muted-foreground">The default 200-day rule is declared before the data request. Run it once, then evaluate the result against SPY rather than optimizing for the highest historical ROI.</p></CardContent></Card>}
    </main>
  )
}

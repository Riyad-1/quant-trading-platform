'use client'

import { FormEvent, useEffect, useState } from 'react'
import { Banknote, CandlestickChart, CircleDollarSign, RefreshCw, Send, ShieldCheck } from 'lucide-react'
import MetricCard from '@/components/MetricCard'
import PageHeader from '@/components/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '@/components/PanelState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api, apiErrorMessage, PaperSummary } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'

export default function PaperTradingPage() {
  const [summary, setSummary] = useState<PaperSummary | null>(null)
  const [ticker, setTicker] = useState('SPY')
  const [price, setPrice] = useState(500)
  const [quantity, setQuantity] = useState(10)
  const [sector, setSector] = useState('ETF')
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [loading, setLoading] = useState(true)
  const [action, setAction] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function load() {
    setLoading(true); setError('')
    try { const response = await api.get<PaperSummary>('/api/v1/paper/summary'); setSummary(response.data) }
    catch (requestError) { setError(apiErrorMessage(requestError)) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function submit(event: FormEvent) {
    event.preventDefault(); setAction(true); setError(''); setMessage('')
    try {
      const response = await api.post<{ order: { status: string; rejection_reason?: string }; summary: PaperSummary }>('/api/v1/paper/orders', { ticker, price, quantity, sector, side, order_type: 'market' })
      setSummary(response.data.summary)
      setMessage(response.data.order.status === 'filled' ? `${side.toUpperCase()} order filled` : response.data.order.rejection_reason || `Order ${response.data.order.status}`)
    } catch (requestError) { setError(apiErrorMessage(requestError)) } finally { setAction(false) }
  }

  async function reset() {
    if (!window.confirm('Reset the in-memory paper portfolio to $100,000?')) return
    try { const response = await api.post<PaperSummary>('/api/v1/paper/reset', { initial_capital: 100000 }); setSummary(response.data); setMessage('Paper portfolio reset') }
    catch (requestError) { setError(apiErrorMessage(requestError)) }
  }

  return (
    <main>
      <PageHeader eyebrow="Execution sandbox" title="Paper trading" description="Test order sizing, commission, slippage and concentration constraints without sending an order to a broker. Prices are entered manually and state lives only in the API process memory." actions={<Badge tone="warning">Simulation · no broker</Badge>} />
      {loading ? <Card className="mt-6"><LoadingState label="Loading paper account" /></Card> : error && !summary ? <Card className="mt-6"><ErrorState message={error} /></Card> : summary && <>
        <section className="section-grid"><MetricCard label="Total equity" value={formatCurrency(summary.total_value)} detail={`${summary.total_pnl_pct.toFixed(2)}% total P&L`} icon={CircleDollarSign} tone={summary.total_pnl >= 0 ? 'positive' : 'negative'} /><MetricCard label="Available cash" value={formatCurrency(summary.cash)} detail="Before new orders" icon={Banknote} /><MetricCard label="Open positions" value={String(summary.num_positions)} detail="Maximum 20" icon={CandlestickChart} /><MetricCard label="Risk model" value="Active" detail="Position and sector limits" icon={ShieldCheck} tone="positive" /></section>
        <div className="mt-6 grid gap-6 xl:grid-cols-[.55fr_1.45fr]"><Card><CardHeader><CardTitle>Order ticket</CardTitle><CardDescription>Market orders fill immediately at the supplied price plus modeled slippage.</CardDescription></CardHeader><CardContent><form onSubmit={submit} className="space-y-4"><div className="grid grid-cols-2 gap-3"><label><span className="label">Ticker</span><input className="field" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} /></label><label><span className="label">Sector</span><input className="field" value={sector} onChange={(e) => setSector(e.target.value)} /></label><label><span className="label">Price</span><input className="field" type="number" min="0.01" step="0.01" value={price} onChange={(e) => setPrice(Number(e.target.value))} /></label><label><span className="label">Quantity</span><input className="field" type="number" min="1" value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} /></label></div><div className="grid grid-cols-2 gap-2"><Button type="button" variant={side === 'buy' ? 'primary' : 'secondary'} onClick={() => setSide('buy')}>Buy</Button><Button type="button" variant={side === 'sell' ? 'danger' : 'secondary'} onClick={() => setSide('sell')}>Sell</Button></div><Button className="w-full" type="submit" disabled={action}><Send size={15} />{action ? 'Submitting…' : `Submit ${side}`}</Button>{message && <p className="rounded-lg border border-cyan-400/15 bg-cyan-400/5 p-3 text-xs text-cyan-200">{message}</p>}{error && <p className="text-xs text-rose-300">{error}</p>}<Button className="w-full" type="button" variant="ghost" size="sm" onClick={reset}><RefreshCw size={14} />Reset account</Button></form></CardContent></Card>
        <Card className="overflow-hidden"><CardHeader><CardTitle>Open positions</CardTitle><CardDescription>{summary.notice}</CardDescription></CardHeader>{!summary.positions.length ? <EmptyState title="No open positions" detail="Enter a current price and submit a buy order. The risk engine may reject oversized positions." /> : <Table><TableHeader><TableRow><TableHead>Symbol</TableHead><TableHead>Quantity</TableHead><TableHead>Average cost</TableHead><TableHead>Current price</TableHead><TableHead>Market value</TableHead><TableHead>Unrealized P&L</TableHead></TableRow></TableHeader><TableBody>{summary.positions.map((position) => <TableRow key={position.ticker}><TableCell className="font-semibold text-white">{position.ticker}</TableCell><TableCell>{position.quantity}</TableCell><TableCell className="font-mono">{formatCurrency(position.avg_cost)}</TableCell><TableCell className="font-mono">{formatCurrency(position.current_price)}</TableCell><TableCell className="font-mono">{formatCurrency(position.current_price * position.quantity)}</TableCell><TableCell className={position.unrealized_pnl >= 0 ? 'font-mono text-emerald-300' : 'font-mono text-rose-300'}>{formatCurrency(position.unrealized_pnl)} <span className="text-xs">({position.unrealized_pnl_pct.toFixed(2)}%)</span></TableCell></TableRow>)}</TableBody></Table>}</Card></div>
      </>}
    </main>
  )
}

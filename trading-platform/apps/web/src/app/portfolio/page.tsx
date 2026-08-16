'use client'

import { FormEvent, useEffect, useState } from 'react'
import { Briefcase, CircleDollarSign, Database, Layers3, Plus } from 'lucide-react'
import Chart from '@/components/Chart'
import MetricCard from '@/components/MetricCard'
import PageHeader from '@/components/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '@/components/PanelState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api, apiErrorMessage, Portfolio, PortfolioPosition, PortfolioSnapshot } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'

export default function PortfolioPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [positions, setPositions] = useState<PortfolioPosition[]>([])
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([])
  const [name, setName] = useState('Research Portfolio')
  const [initialCash, setInitialCash] = useState(100000)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  async function loadPortfolios() {
    setLoading(true); setError('')
    try {
      const response = await api.get<Portfolio[]>('/api/v1/portfolio')
      setPortfolios(response.data)
      setSelectedId((current) => current ?? response.data[0]?.id ?? null)
    } catch (requestError) { setError(apiErrorMessage(requestError)) } finally { setLoading(false) }
  }
  useEffect(() => { loadPortfolios() }, [])
  useEffect(() => {
    if (!selectedId) { setPositions([]); setSnapshots([]); return }
    Promise.all([api.get<PortfolioPosition[]>(`/api/v1/portfolio/${selectedId}/positions`), api.get<PortfolioSnapshot[]>(`/api/v1/portfolio/${selectedId}/snapshots`)]).then(([positionResponse, snapshotResponse]) => { setPositions(positionResponse.data); setSnapshots(snapshotResponse.data) }).catch((requestError) => setError(apiErrorMessage(requestError)))
  }, [selectedId])

  async function createPortfolio(event: FormEvent) {
    event.preventDefault(); setCreating(true); setError('')
    try {
      const response = await api.post<Portfolio>('/api/v1/portfolio', { name, initial_cash: initialCash })
      await loadPortfolios(); setSelectedId(response.data.id)
    } catch (requestError) { setError(apiErrorMessage(requestError)) } finally { setCreating(false) }
  }

  const selected = portfolios.find((portfolio) => portfolio.id === selectedId) || null
  return (
    <main>
      <PageHeader eyebrow="Persistent account view" title="Portfolio intelligence" description="Create PostgreSQL-backed research portfolios and inspect their recorded positions and equity snapshots. Order placement remains in the separate paper-execution sandbox." actions={<Badge tone="positive">PostgreSQL persistence</Badge>} />
      {loading ? <Card className="mt-6"><LoadingState label="Loading portfolios" /></Card> : error && !portfolios.length ? <Card className="mt-6"><ErrorState message={error} /></Card> : <>
        <Card className="mt-6"><CardContent className="pt-5"><form onSubmit={createPortfolio} className="grid items-end gap-4 lg:grid-cols-[1fr_220px_auto]"><label><span className="label">Portfolio name</span><input className="field" value={name} onChange={(e) => setName(e.target.value)} /></label><label><span className="label">Initial cash</span><input className="field" type="number" min={1000} value={initialCash} onChange={(e) => setInitialCash(Number(e.target.value))} /></label><Button disabled={creating}><Plus size={15} />{creating ? 'Creating…' : 'Create portfolio'}</Button></form>{error && <p className="mt-3 text-xs text-rose-300">{error}</p>}</CardContent></Card>
        {!portfolios.length ? <Card className="mt-6"><EmptyState title="No persistent portfolios" detail="Create the first PostgreSQL-backed portfolio with the form above." /></Card> : <>
          <div className="mt-6 flex gap-2 overflow-x-auto pb-2">{portfolios.map((portfolio) => <button key={portfolio.id} onClick={() => setSelectedId(portfolio.id)} className={`shrink-0 rounded-xl border px-4 py-3 text-left transition ${selectedId === portfolio.id ? 'border-primary/30 bg-primary/10' : 'border-white/5 bg-white/[0.02] hover:bg-white/[0.04]'}`}><p className="text-sm font-medium text-white">{portfolio.name}</p><p className="mt-1 text-xs text-muted-foreground">{formatCurrency(portfolio.total_equity ?? portfolio.initial_cash)}</p></button>)}</div>
          {selected && <><section className="section-grid"><MetricCard label="Total equity" value={formatCurrency(selected.total_equity ?? selected.initial_cash)} detail="Latest stored value" icon={CircleDollarSign} /><MetricCard label="Available cash" value={formatCurrency(selected.current_cash ?? selected.initial_cash)} detail="Persistent ledger" icon={Database} /><MetricCard label="Positions" value={String(positions.length)} detail="Recorded holdings" icon={Layers3} /><MetricCard label="Snapshots" value={String(snapshots.length)} detail="Equity observations" icon={Briefcase} /></section>
          <div className="mt-6 grid gap-6 xl:grid-cols-2"><Card><CardHeader><CardTitle>Equity history</CardTitle><CardDescription>Portfolio snapshots recorded by backend jobs or execution flows.</CardDescription></CardHeader><CardContent>{snapshots.length ? <Chart data={[...snapshots].reverse().map((snapshot) => ({ date: snapshot.time.slice(0, 10), equity: snapshot.equity ?? 0 }))} /> : <EmptyState title="No equity snapshots" detail="This portfolio exists, but no snapshot-writing workflow has recorded its history yet." />}</CardContent></Card><Card className="overflow-hidden"><CardHeader><CardTitle>Positions</CardTitle><CardDescription>Database records associated with this portfolio.</CardDescription></CardHeader>{positions.length ? <Table><TableHeader><TableRow><TableHead>Asset ID</TableHead><TableHead>Quantity</TableHead><TableHead>Entry</TableHead><TableHead>Status</TableHead><TableHead>Realized P&L</TableHead></TableRow></TableHeader><TableBody>{positions.map((position) => <TableRow key={position.id}><TableCell className="font-mono">{position.asset_id}</TableCell><TableCell>{position.quantity}</TableCell><TableCell className="font-mono">{formatCurrency(position.entry_price)}</TableCell><TableCell><Badge tone={position.status === 'open' ? 'positive' : 'neutral'}>{position.status}</Badge></TableCell><TableCell className="font-mono">{position.pnl_realized == null ? '—' : formatCurrency(position.pnl_realized)}</TableCell></TableRow>)}</TableBody></Table> : <EmptyState title="No recorded positions" detail="Use the paper engine for simulation. Persistence wiring between the engines remains a separate integration boundary." />}</Card></div></>}
        </>}
      </>}
    </main>
  )
}

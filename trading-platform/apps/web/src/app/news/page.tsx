'use client'

import { useEffect, useState } from 'react'
import { ExternalLink, Filter, Newspaper, RefreshCw, Sparkles } from 'lucide-react'
import PageHeader from '@/components/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '@/components/PanelState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { api, apiErrorMessage, NewsArticle } from '@/lib/api'

export default function NewsPage() {
  const [articles, setArticles] = useState<NewsArticle[]>([])
  const [ticker, setTicker] = useState('')
  const [loading, setLoading] = useState(true)
  const [action, setAction] = useState('')
  const [error, setError] = useState('')

  async function loadArticles() {
    setLoading(true); setError('')
    try { const response = await api.get<NewsArticle[]>('/api/v1/news/articles', { params: { ticker: ticker || undefined, limit: 50 } }); setArticles(response.data) }
    catch (requestError) { setError(apiErrorMessage(requestError)) } finally { setLoading(false) }
  }
  useEffect(() => {
    let active = true
    api.get<NewsArticle[]>('/api/v1/news/articles', { params: { limit: 50 } })
      .then((response) => { if (active) setArticles(response.data) })
      .catch((requestError) => { if (active) setError(apiErrorMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function ingest() {
    setAction('ingest'); setError('')
    try { await api.post('/api/v1/news/ingest', null, { params: { limit: 25 } }); await loadArticles() }
    catch (requestError) { setError(apiErrorMessage(requestError)) } finally { setAction('') }
  }
  async function processEvents() {
    setAction('process'); setError('')
    try { await api.post('/api/v1/news/process-events', null, { params: { limit: 100 } }); await loadArticles() }
    catch (requestError) { setError(apiErrorMessage(requestError)) } finally { setAction('') }
  }

  return (
    <main>
      <PageHeader eyebrow="Catalyst intelligence" title="News and events" description="Ingest articles from the recovered mock provider, then extract structured events with the rule-based processor. LLM extraction remains disabled until a provider and API key are configured." actions={<Badge tone="warning">Mock news · rules only</Badge>} />
      <Card className="mt-6"><CardContent className="flex flex-col gap-4 pt-5 lg:flex-row lg:items-end"><label className="flex-1"><span className="label">Filter ticker</span><input className="field" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="AAPL" /></label><Button variant="secondary" onClick={loadArticles} disabled={loading}><Filter size={15} />Apply filter</Button><Button variant="secondary" onClick={ingest} disabled={Boolean(action)}><RefreshCw size={15} className={action === 'ingest' ? 'animate-spin' : ''} />Ingest mock feed</Button><Button onClick={processEvents} disabled={Boolean(action)}><Sparkles size={15} />Process events</Button></CardContent></Card>
      <Card className="mt-6"><CardHeader><CardTitle>Article stream</CardTitle><CardDescription>{articles.length} stored articles{ticker ? ` linked to ${ticker}` : ''}. Processing status is shown per record.</CardDescription></CardHeader>{loading ? <LoadingState label="Loading stored articles" /> : error ? <ErrorState message={error} /> : !articles.length ? <EmptyState title="No articles stored" detail="Use “Ingest mock feed” to load the provider’s deterministic research fixtures." /> : <CardContent className="space-y-3">{articles.map((article) => <article key={article.id} className="rounded-xl border border-white/5 bg-white/[0.018] p-4 transition hover:bg-white/[0.035]"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><div className="mb-2 flex flex-wrap items-center gap-2">{article.tickers.map((symbol) => <Badge key={symbol} tone="info">{symbol}</Badge>)}<Badge tone={article.is_processed ? 'positive' : 'neutral'}>{article.is_processed ? 'Processed' : 'Pending'}</Badge></div><h3 className="font-medium text-slate-100">{article.headline}</h3>{article.summary && <p className="mt-2 max-w-4xl text-sm leading-6 text-muted-foreground">{article.summary}</p>}<p className="mt-3 text-xs text-slate-600">{new Date(article.published_at).toLocaleString()}</p></div>{article.url && <a href={article.url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-primary"><ExternalLink size={16} /></a>}</div></article>)}</CardContent>}</Card>
      <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground"><Newspaper size={14} />This module does not claim live or comprehensive market news coverage.</div>
    </main>
  )
}

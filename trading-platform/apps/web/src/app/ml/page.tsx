'use client'

import { useEffect, useState } from 'react'
import { BrainCircuit, CheckCircle2, DatabaseZap, FlaskConical, Layers3, RefreshCw } from 'lucide-react'
import MetricCard from '@/components/MetricCard'
import PageHeader from '@/components/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '@/components/PanelState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api, apiErrorMessage, MLStatus, ModelMetadata } from '@/lib/api'
import { titleCase } from '@/lib/utils'

interface RegistryResponse { total_models: number; active_models: number; models: ModelMetadata[] }

export default function MachineLearningPage() {
  const [status, setStatus] = useState<MLStatus | null>(null)
  const [models, setModels] = useState<ModelMetadata[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const [statusResponse, registryResponse] = await Promise.all([api.get<MLStatus>('/api/v1/ml/status'), api.get<RegistryResponse>('/api/v1/ml/models')])
      setStatus(statusResponse.data); setModels(registryResponse.data.models)
    } catch (requestError) { setError(apiErrorMessage(requestError)) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function activate(modelId: string) {
    try { await api.post(`/api/v1/ml/models/${encodeURIComponent(modelId)}/activate`); await load() }
    catch (requestError) { setError(apiErrorMessage(requestError)) }
  }

  return (
    <main>
      <PageHeader eyebrow="Model governance" title="Machine-learning laboratory" description="Inspect the recovered classification stack and registry without manufacturing predictions. A model only becomes available after point-in-time features, targets and walk-forward validation have been supplied by the training pipeline." actions={<Badge tone={status?.status === 'ready' ? 'positive' : 'warning'}>{status ? titleCase(status.status) : 'Checking'}</Badge>} />
      {loading ? <Card className="mt-6"><LoadingState label="Inspecting model registry" /></Card> : error ? <Card className="mt-6"><ErrorState message={error} /></Card> : status && <>
        <section className="section-grid"><MetricCard label="Registered" value={String(status.registered_models)} detail="Versioned models" icon={Layers3} /><MetricCard label="Active" value={String(status.active_models)} detail="Eligible for inference" icon={CheckCircle2} tone={status.active_models ? 'positive' : 'default'} /><MetricCard label="Estimators" value={String(status.supported_models.length)} detail={status.supported_models.map(titleCase).join(', ')} icon={BrainCircuit} /><MetricCard label="Validation" value="Walk-forward" detail="Time-series aware splits" icon={FlaskConical} /></section>
        <div className="mt-6 grid gap-6 xl:grid-cols-[.65fr_1.35fr]"><Card><CardHeader><CardTitle>Training boundary</CardTitle><CardDescription>Required before the interface will expose predictions.</CardDescription></CardHeader><CardContent className="space-y-4">{[['Point-in-time dataset', 'Features and outcomes aligned without future leakage.'], ['Walk-forward validation', 'Train and validation windows progress through time.'], ['Model registration', 'Metrics, horizon and feature count stored with the artifact.'], ['Explicit activation', 'Only one reviewed model per horizon becomes active.']].map(([title, detail], index) => <div key={title} className="flex gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-primary/20 bg-primary/10 font-mono text-xs text-primary">{index + 1}</span><div><p className="text-sm font-medium text-slate-200">{title}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</p></div></div>)}<div className="rounded-xl border border-amber-400/15 bg-amber-400/5 p-4 text-xs leading-5 text-amber-200/80"><DatabaseZap className="mb-2" size={17} />Training is intentionally unavailable in the UI until real, point-in-time feature history exists.</div></CardContent></Card>
        <Card className="overflow-hidden"><CardHeader className="flex-row items-start justify-between"><div><CardTitle>Model registry</CardTitle><CardDescription>{status.notice}</CardDescription></div><Button variant="ghost" size="sm" onClick={load}><RefreshCw size={14} />Refresh</Button></CardHeader>{!models.length ? <EmptyState title="No trained models" detail="The registry is working, but no model artifact has passed through the recovered training pipeline yet." /> : <Table><TableHeader><TableRow><TableHead>Model</TableHead><TableHead>Horizon</TableHead><TableHead>AUC</TableHead><TableHead>Accuracy</TableHead><TableHead>Features</TableHead><TableHead>Status</TableHead></TableRow></TableHeader><TableBody>{models.map((model) => <TableRow key={model.model_id}><TableCell><p className="font-medium text-white">{model.model_id}</p><p className="text-xs text-muted-foreground">{titleCase(model.model_type)}</p></TableCell><TableCell>{model.horizon_days} days</TableCell><TableCell className="font-mono">{model.val_auc.toFixed(3)}</TableCell><TableCell className="font-mono">{model.val_accuracy.toFixed(3)}</TableCell><TableCell>{model.feature_count}</TableCell><TableCell>{model.is_active ? <Badge tone="positive">Active</Badge> : <Button variant="secondary" size="sm" onClick={() => activate(model.model_id)}>Activate</Button>}</TableCell></TableRow>)}</TableBody></Table>}</Card></div>
      </>}
    </main>
  )
}

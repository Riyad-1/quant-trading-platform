import { LucideIcon } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  value: string
  detail?: string
  icon?: LucideIcon
  tone?: 'default' | 'positive' | 'negative'
}

export default function MetricCard({ label, value, detail, icon: Icon, tone = 'default' }: MetricCardProps) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
          <p className={cn('mt-2 font-mono text-2xl font-semibold', tone === 'positive' && 'text-emerald-300', tone === 'negative' && 'text-rose-300')}>{value}</p>
          {detail && <p className="mt-1 text-xs text-muted-foreground">{detail}</p>}
        </div>
        {Icon && <span className="rounded-xl border border-primary/20 bg-primary/10 p-2.5 text-primary"><Icon size={18} /></span>}
      </div>
    </Card>
  )
}

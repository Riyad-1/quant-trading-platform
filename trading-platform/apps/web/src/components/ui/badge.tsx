import * as React from 'react'
import { cn } from '@/lib/utils'

export function Badge({
  className,
  tone = 'neutral',
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: 'neutral' | 'positive' | 'warning' | 'negative' | 'info' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider',
        tone === 'neutral' && 'border-white/10 bg-white/5 text-muted-foreground',
        tone === 'positive' && 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
        tone === 'warning' && 'border-amber-400/20 bg-amber-400/10 text-amber-300',
        tone === 'negative' && 'border-rose-400/20 bg-rose-400/10 text-rose-300',
        tone === 'info' && 'border-cyan-400/20 bg-cyan-400/10 text-cyan-300',
        className,
      )}
      {...props}
    />
  )
}

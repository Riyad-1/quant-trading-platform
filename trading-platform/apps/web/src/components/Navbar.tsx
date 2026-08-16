'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Activity, BarChart3, BrainCircuit, Briefcase, CandlestickChart, LayoutDashboard, Newspaper, Radio, ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'

const links = [
  { href: '/', label: 'Overview', icon: LayoutDashboard },
  { href: '/scanner', label: 'Scanner', icon: Radio },
  { href: '/backtest', label: 'Backtest', icon: BarChart3 },
  { href: '/regime', label: 'Regime', icon: Activity },
  { href: '/news', label: 'News', icon: Newspaper },
  { href: '/ml', label: 'ML Lab', icon: BrainCircuit },
  { href: '/paper', label: 'Paper', icon: CandlestickChart },
  { href: '/portfolio', label: 'Portfolio', icon: Briefcase },
]

export default function Navbar() {
  const pathname = usePathname()
  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-background/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1500px] items-center gap-6 px-4 py-3 lg:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-cyan-300 to-indigo-500 text-slate-950 shadow-glow"><ShieldCheck size={20} /></span>
          <span className="hidden sm:block"><span className="block text-sm font-semibold tracking-tight text-white">Quant Console</span><span className="block text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Research, not advice</span></span>
        </Link>
        <nav className="flex flex-1 items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
          {links.map(({ href, label, icon: Icon }) => {
            const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
            return <Link key={href} href={href} className={cn('flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition', active ? 'bg-primary/12 text-cyan-200' : 'text-muted-foreground hover:bg-white/5 hover:text-slate-200')}><Icon size={15} />{label}</Link>
          })}
        </nav>
        <a href={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/docs`} target="_blank" className="hidden shrink-0 items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-muted-foreground transition hover:border-primary/30 hover:text-white xl:flex"><Activity size={14} />API</a>
      </div>
    </header>
  )
}

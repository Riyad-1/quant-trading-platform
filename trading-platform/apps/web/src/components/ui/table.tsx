import * as React from 'react'
import { cn } from '@/lib/utils'

export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return <table className={cn('w-full text-left text-sm', className)} {...props} />
}
export function TableHeader(props: React.HTMLAttributes<HTMLTableSectionElement>) { return <thead {...props} /> }
export function TableBody(props: React.HTMLAttributes<HTMLTableSectionElement>) { return <tbody {...props} /> }
export function TableRow({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn('border-b border-white/5 transition hover:bg-white/[0.025]', className)} {...props} />
}
export function TableHead({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn('px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground', className)} {...props} />
}
export function TableCell({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('px-4 py-3.5', className)} {...props} />
}

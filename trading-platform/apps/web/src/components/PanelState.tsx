import { AlertTriangle, Loader2 } from 'lucide-react'

export function LoadingState({ label = 'Loading data' }: { label?: string }) {
  return <div className="flex min-h-40 items-center justify-center gap-3 text-sm text-muted-foreground"><Loader2 className="animate-spin" size={18} />{label}</div>
}

export function ErrorState({ message }: { message: string }) {
  return <div className="flex min-h-40 items-center justify-center gap-3 px-6 text-center text-sm text-rose-300"><AlertTriangle size={18} />{message}</div>
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="flex min-h-40 flex-col items-center justify-center px-6 text-center"><p className="font-medium text-slate-200">{title}</p><p className="mt-2 max-w-md text-sm text-muted-foreground">{detail}</p></div>
}

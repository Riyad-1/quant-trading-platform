import * as React from 'react'
import { cn } from '@/lib/utils'

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  size?: 'sm' | 'md'
}

export function Button({ className, variant = 'primary', size = 'md', ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm',
        variant === 'primary' && 'bg-primary text-primary-foreground hover:bg-primary/90',
        variant === 'secondary' && 'border border-white/10 bg-white/5 text-foreground hover:bg-white/10',
        variant === 'danger' && 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        variant === 'ghost' && 'text-muted-foreground hover:bg-white/5 hover:text-foreground',
        className,
      )}
      {...props}
    />
  )
}

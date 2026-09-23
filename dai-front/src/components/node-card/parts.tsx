import { gidParts } from '@/lib/format'
import { cn } from '@/lib/utils'

export function Gid({ gid, className }: { gid: string; className?: string }) {
  const p = gidParts(gid)
  return (
    <span className={cn('font-mono whitespace-nowrap', className)}>
      <span className="text-muted-foreground">{p.pre}</span>
      <span className="font-bold">{p.mid}</span>
      <span className="text-muted-foreground">{p.suf}</span>
    </span>
  )
}

export function SeedPill({ small }: { small?: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center border-[1.5px] border-primary font-mono font-semibold text-primary',
        small ? 'rounded-lg px-1.5 text-[10.5px]' : 'h-6.5 rounded-full px-2.5 text-xs',
      )}
    >
      SEED
    </span>
  )
}

export function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-[12.5px] font-medium text-muted-foreground">{children}</div>
}

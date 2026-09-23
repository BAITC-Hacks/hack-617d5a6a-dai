import { roleSymbolPath, roleVar, type Role } from '@/lib/roles'
import { cn } from '@/lib/utils'

/** Значок роли — та же форма и цвет, что у узла на графе. Размер задаётся className (по умолчанию 12px). */
export function RoleIcon({ role, className }: { role: Role | null | undefined; className?: string }) {
  const { d, rotate } = roleSymbolPath(role, 5.6)
  return (
    <svg viewBox="-8 -8 16 16" aria-hidden className={cn('size-3 flex-none', className)}>
      <path d={d} transform={rotate ? `rotate(${rotate})` : undefined} style={{ fill: roleVar(role) }} />
    </svg>
  )
}

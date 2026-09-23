import type { NodeOut } from '@/client/types.gen'

export type Role = NodeOut['role']

// Порядок легенды и фильтров: редкие смысловые роли первыми, массовые — в конце.
export const ROLE_ORDER: Role[] = ['coordinator', 'distributor', 'consolidator', 'transit', 'terminal', 'peripheral']

// Подписи и описания отдаёт /meta (roles[]); здесь — запасные, пока /meta не пришёл.
export const ROLE_FALLBACK_TITLE: Record<Role, string> = {
  coordinator: 'Координатор',
  distributor: 'Распределитель',
  consolidator: 'Консолидатор',
  transit: 'Транзит',
  terminal: 'Конечный получатель',
  peripheral: 'Периферия',
}

// Статичные строки классов: Tailwind видит только целые имена классов в исходниках.
export const ROLE_CLASS: Record<Role, { dot: string; badge: string; ink: string }> = {
  coordinator: { dot: 'bg-role-coordinator', badge: 'bg-role-coordinator-tint text-role-coordinator-ink', ink: 'text-role-coordinator-ink' },
  distributor: { dot: 'bg-role-distributor', badge: 'bg-role-distributor-tint text-role-distributor-ink', ink: 'text-role-distributor-ink' },
  consolidator: { dot: 'bg-role-consolidator', badge: 'bg-role-consolidator-tint text-role-consolidator-ink', ink: 'text-role-consolidator-ink' },
  transit: { dot: 'bg-role-transit', badge: 'bg-role-transit-tint text-role-transit-ink', ink: 'text-role-transit-ink' },
  terminal: { dot: 'bg-role-terminal', badge: 'bg-role-terminal-tint text-role-terminal-ink', ink: 'text-role-terminal-ink' },
  peripheral: { dot: 'bg-role-peripheral', badge: 'bg-role-peripheral-tint text-role-peripheral-ink', ink: 'text-role-peripheral-ink' },
}

export const UNKNOWN_ROLE_CLASS = { dot: 'bg-muted-foreground/40', badge: 'bg-muted text-muted-foreground', ink: 'text-muted-foreground' }

export const roleClass = (role: Role | null | undefined) => (role ? ROLE_CLASS[role] : UNKNOWN_ROLE_CLASS)

/** Цвет роли для D3/SVG: `selection.style('fill', roleVar(role))`. Внутри `.dark` берётся тёмный вариант. */
export const roleVar = (role: Role | null | undefined) => (role ? `var(--role-${role})` : 'var(--muted-foreground)')

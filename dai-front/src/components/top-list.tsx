import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { RoleIcon } from '@/components/role-icon'
import { Skeleton } from '@/components/ui/skeleton'
import { formatScore, gidParts } from '@/lib/format'
import { errorKind, metaQuery, useQueue, useRoleInfo } from '@/lib/graph-data'
import { roleClass } from '@/lib/roles'
import { cn } from '@/lib/utils'

/** gid моноширинно: общий префикс и хвост приглушены, середина жирная. */
export function GidText({ gid, className }: { gid: string; className?: string }) {
  const p = gidParts(gid)
  return (
    <span className={cn('font-mono font-medium', className)}>
      <span className="text-muted-foreground">{p.pre}</span>
      <span className="font-bold">{p.mid}</span>
      <span className="text-muted-foreground">{p.suf}</span>
    </span>
  )
}

export function SeedPill() {
  return <span className="rounded-full border-[1.5px] border-primary px-1.5 font-mono text-[11px] font-semibold">SEED</span>
}

/** Правило очереди коротко: первая фраза до скобок, с заглавной. Полный текст — в title. */
const shortRule = (rule: string) => {
  const s = rule.split(' (')[0]
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** evidence без префикса роли («координатор (gather-scatter): …») — роль уже видна бейджем. */
const evidenceBody = (evidence: string) => evidence.replace(/^[^:;]*:\s*/, '')

export function TopList({ activeGid }: { activeGid: string }) {
  const { queue, isPending, error } = useQueue()
  const { data: meta } = useQuery(metaQuery())
  const roleInfo = useRoleInfo()
  const navigate = useNavigate()
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [activeGid, queue])

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-1 px-4 pt-3.5 pb-2.5">
        <div className="flex items-baseline gap-2">
          <h2 className="text-[15px] font-semibold whitespace-nowrap">Очередь проверки{queue.length > 0 && ` · ${queue.length}`}</h2>
          <div className="ml-auto text-[12.5px] whitespace-nowrap text-muted-foreground">по priority_score</div>
        </div>
        {meta?.queue_rule && (
          <p title={meta.queue_rule} className="line-clamp-2 text-xs/[1.45] text-muted-foreground">
            {shortRule(meta.queue_rule)}
          </p>
        )}
      </div>
      <div ref={listRef} className="min-h-0 flex-1 overflow-auto border-t">
        {isPending &&
          Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="flex flex-col gap-2 border-b border-border/60 px-4 py-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-5 w-1/2" />
              <Skeleton className="h-3 w-full" />
            </div>
          ))}
        {error && (
          <p className="px-4 py-3 text-sm text-muted-foreground">
            {errorKind(error) === 'down' ? 'Сервер анализа недоступен — очередь не загружена.' : 'Не удалось загрузить очередь.'}
          </p>
        )}
        {queue.map((n, i) => {
          const rc = roleClass(n.role)
          const { title, description } = roleInfo(n.role)
          const active = n.gid === activeGid
          return (
            <button
              key={n.gid}
              type="button"
              aria-current={active}
              onClick={() => navigate({ to: '/nodes/$gid', params: { gid: n.gid } })}
              className={cn(
                'grid w-full grid-cols-[26px_minmax(0,1fr)_auto] gap-x-2.5 gap-y-1 border-b border-border/60 px-4 pt-[11px] pb-3 text-left hover:bg-muted/60',
                active && 'bg-muted shadow-[inset_3px_0_0_var(--color-primary)] hover:bg-muted',
              )}
            >
              <div className="pt-px font-mono text-sm font-semibold text-muted-foreground">{i + 1}</div>
              <GidText gid={n.gid} className="truncate text-[15px]" />
              <div className="text-right font-mono text-[15px] font-bold">{formatScore(n.priority_score)}</div>
              <div />
              <div className="col-span-2 flex items-center gap-2">
                <span title={description} className={cn('inline-flex h-[22px] items-center gap-1.5 rounded-md pr-2 pl-1.5 text-[12.5px] font-semibold whitespace-nowrap', rc.badge)}>
                  <RoleIcon role={n.role} className="size-3" />
                  {title}
                </span>
                {n.is_seed && <SeedPill />}
                <span className="ml-auto h-1 w-16 shrink-0 overflow-hidden rounded-sm bg-foreground/10">
                  <span className="block h-full bg-foreground/80" style={{ width: `${Math.min(100, Math.round(n.priority_score * 100))}%` }} />
                </span>
              </div>
              <div />
              <div title={n.evidence} className="col-span-2 line-clamp-2 font-mono text-xs/[1.45] text-muted-foreground">
                {evidenceBody(n.evidence)}
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}

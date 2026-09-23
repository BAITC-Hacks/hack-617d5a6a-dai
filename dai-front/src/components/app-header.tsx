import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { LegendEntry, LegendSheet, type LegendItem } from '@/components/role-legend'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDayLong, formatInt, formatKztCompact } from '@/lib/format'
import { metaQuery } from '@/lib/graph-data'
import { ROLE_ORDER } from '@/lib/roles'

/** «2026-07-01», «2026-07-31» → «1–31 июля 2026». */
function formatPeriod(start: string, end: string) {
  const year = end.slice(0, 4)
  return start.slice(0, 7) === end.slice(0, 7)
    ? `${Number(start.slice(8, 10))}–${formatDayLong(end)} ${year}`
    : `${formatDayLong(start)} – ${formatDayLong(end)} ${year}`
}

export function AppHeader() {
  const { data: meta } = useQuery(metaQuery())
  const [legendItem, setLegendItem] = useState<LegendItem | null>(null)

  const stats = meta
    ? [
        [formatInt(meta.n_nodes), 'клиентов'],
        [formatInt(meta.n_edges), 'связей'],
        [formatInt(meta.n_transactions), 'переводов'],
        [formatInt(meta.n_seed), 'seed'],
        [formatInt(meta.n_clusters), 'кластеров'],
        [formatKztCompact(meta.total_kzt), `· ${formatPeriod(meta.period_start, meta.period_end)}`],
      ]
    : []

  return (
    <>
      <header className="flex h-14 flex-none items-center gap-6 border-b bg-background px-5">
        <div className="flex items-center gap-2.5">
          <div className="grid size-7 place-items-center rounded-[7px] bg-primary text-[15px] font-semibold text-primary-foreground">₸</div>
          <div className="text-[17px] font-semibold tracking-tight whitespace-nowrap">Граф денег</div>
        </div>
        <nav className="flex gap-1">
          <span className="flex h-8 items-center rounded-[7px] bg-muted px-3 text-sm font-semibold">Узел</span>
        </nav>
        <div className="ml-auto flex items-center gap-[18px]">
          {meta ? (
            stats.map(([v, l]) => (
              <div key={l} className="flex items-baseline gap-1.5 whitespace-nowrap">
                <span className="font-mono text-[15px] font-semibold">{v}</span>
                <span className="text-[13px] text-muted-foreground">{l}</span>
              </div>
            ))
          ) : (
            <Skeleton className="h-4 w-[520px]" />
          )}
        </div>
      </header>

      <div className="flex min-h-11 flex-none flex-wrap items-center gap-[18px] border-b bg-muted/40 px-5 py-1.5">
        <div className="flex flex-wrap items-center gap-4">
          {ROLE_ORDER.map((role) => (
            <LegendEntry key={role} item={role} onOpen={setLegendItem} />
          ))}
        </div>
        <span className="h-5 w-px bg-border" />
        <LegendEntry item="seed" onOpen={setLegendItem} />
        <LegendEntry item="boundary" onOpen={setLegendItem} />
        <LegendSheet item={legendItem} onClose={() => setLegendItem(null)} />
        {meta?.mock && (
          // Статус данных, а не элемент темы — поэтому янтарные утилиты.
          <div className="ml-auto flex h-[30px] items-center gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/10 pr-3 pl-1">
            <span className="flex h-[22px] items-center rounded-[5px] bg-amber-900 px-2 text-xs font-semibold tracking-wide whitespace-nowrap text-amber-50">
              Демо-данные
            </span>
            <span className="text-[13px] font-medium whitespace-nowrap text-amber-900 dark:text-amber-200">
              Роли и приоритеты — заглушка по простым порогам, не результат анализа
            </span>
          </div>
        )}
      </div>
    </>
  )
}

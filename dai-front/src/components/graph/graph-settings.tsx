import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { listClustersOptions } from '@/client/@tanstack/react-query.gen'
import { RoleIcon } from '@/components/role-icon'
import { LegendTooltip } from '@/components/role-legend'
import { graphQuery, useRoleInfo } from '@/lib/graph-data'
import { formatInt } from '@/lib/format'
import { ROLE_ORDER } from '@/lib/roles'
import { cn } from '@/lib/utils'
import { useGraphView, type GraphView } from '@/stores/graph-view'

/** Сегментированный переключатель тёмной панели графа. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: [T, string][]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex rounded-lg border border-border bg-muted p-0.5">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          aria-pressed={v === value}
          onClick={() => onChange(v)}
          className={cn(
            'h-[26px] cursor-pointer whitespace-nowrap rounded-md px-2.5 text-xs font-medium',
            v === value ? 'bg-foreground text-background' : 'text-foreground/80 hover:text-foreground',
          )}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

const pill = (on: boolean) =>
  cn(
    'flex h-[26px] cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-full border px-2 text-xs font-medium',
    on ? 'border-foreground/25 bg-muted text-foreground' : 'border-border text-muted-foreground',
  )

/** Переключает элемент в фильтре; null — «все», пустого фильтра не бывает в null-виде. */
function toggleIn<T>(cur: T[] | null, all: T[], x: T): T[] | null {
  const base = cur ?? all
  const next = base.includes(x) ? base.filter((y) => y !== x) : [...base, x]
  return next.length === all.length ? null : next
}

const times = (v: number) => `×${String(v).replace('.', ',')}`

type Slider = [label: string, key: keyof GraphView, min: number, max: number, step: number, fmt: (v: number) => string]

const DISPLAY_SLIDERS: Slider[] = [
  ['Подписи с приближения', 'labelZoom', 0.4, 3, 0.1, times],
  ['Размер узлов', 'nodeScale', 0.5, 2, 0.1, times],
  ['Толщина связей', 'edgeScale', 0.5, 2.5, 0.1, times],
]
const FORCE_SLIDERS: Slider[] = [
  ['Отталкивание', 'charge', 10, 200, 5, String],
  ['Длина связей', 'linkDist', 15, 120, 5, String],
  ['Притяжение к кластеру', 'clusterPull', 0, 0.4, 0.02, (v) => v.toFixed(2).replace('.', ',')],
]

function Sliders({ items }: { items: Slider[] }) {
  const view = useGraphView((s) => s.view)
  const setView = useGraphView((s) => s.setView)
  return items.map(([label, key, min, max, step, fmt]) => {
    const value = view[key] as number
    return (
      <label key={key} className="flex flex-col gap-1">
        <span className="flex justify-between text-xs font-medium text-foreground/85">
          <span>{label}</span>
          <span className="font-mono text-muted-foreground">{fmt(value)}</span>
        </span>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => setView({ [key]: +e.target.value })}
          className="w-full accent-foreground"
        />
      </label>
    )
  })
}

function Switch({ label, on, onToggle }: { label: string; on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={onToggle}
      className="flex cursor-pointer items-center gap-2.5 py-0.5 text-left text-[13px] font-medium text-foreground/90"
    >
      <span className={cn('relative h-[18px] w-[30px] flex-none rounded-full', on ? 'bg-foreground' : 'bg-muted-foreground/40')}>
        <span className={cn('absolute top-0.5 size-3.5 rounded-full bg-background transition-[left]', on ? 'left-3.5' : 'left-0.5')} />
      </span>
      {label}
    </button>
  )
}

const sectionTitle = 'text-[11.5px] font-semibold tracking-[.06em] text-muted-foreground'
const rowLabel = 'text-xs font-medium text-foreground/85'

export function GraphSettings() {
  const view = useGraphView((s) => s.view)
  const setView = useGraphView((s) => s.setView)
  const toggleSettings = useGraphView((s) => s.toggleSettings)
  const roleInfo = useRoleInfo()
  const { data: graph } = useQuery(graphQuery())
  const { data: clusters } = useQuery({ ...listClustersOptions(), meta: { silent: true } })

  const present = useMemo(
    () => [...new Set((graph?.nodes ?? []).map((n) => n.cluster_id).filter((x) => x != null))].sort((a, b) => a - b),
    [graph],
  )
  const passport = useMemo(() => new Map((clusters?.items ?? []).map((c) => [c.cluster_id, c])), [clusters])

  return (
    <div className="absolute top-2.5 right-2.5 bottom-2.5 flex w-[300px] flex-col overflow-auto rounded-xl border border-border bg-card shadow-2xl">
      <div className="flex items-center border-b border-border px-3.5 py-3">
        <span className="text-sm font-semibold">Настройки графа</span>
        <button
          type="button"
          aria-label="Закрыть настройки"
          onClick={toggleSettings}
          className="ml-auto size-[26px] cursor-pointer rounded-md bg-muted text-sm hover:bg-accent"
        >
          ×
        </button>
      </div>

      <div className="flex flex-col gap-2.5 border-b border-border px-3.5 py-3">
        <div className={sectionTitle}>ФИЛЬТРЫ</div>
        <div className={rowLabel}>Роли</div>
        <div className="flex flex-wrap gap-1.5">
          {ROLE_ORDER.map((r) => {
            const on = !view.roles || view.roles.includes(r)
            return (
              <LegendTooltip key={r} item={r}>
                <button
                  type="button"
                  aria-pressed={on}
                  onClick={() => setView({ roles: toggleIn(view.roles, ROLE_ORDER, r) })}
                  className={pill(on)}
                >
                  <RoleIcon role={r} className={cn('size-3', !on && 'opacity-35')} />
                  {roleInfo(r).title}
                </button>
              </LegendTooltip>
            )
          })}
        </div>
        <div className={rowLabel}>Кластеры</div>
        <div className="flex max-h-40 flex-wrap gap-1.5 overflow-auto">
          {present.map((id) => {
            const on = !view.clusters || view.clusters.includes(id)
            const p = passport.get(id)
            return (
              <button
                key={id}
                type="button"
                aria-pressed={on}
                onClick={() => setView({ clusters: toggleIn(view.clusters, present, id) })}
                className={pill(on)}
              >
                Кластер {id}
                {p && ` · ${formatInt(p.n_nodes)}`}
              </button>
            )
          })}
        </div>
        <Switch label="Показывать seed без связей" on={view.showIsolated} onToggle={() => setView({ showIsolated: !view.showIsolated })} />
        <Switch label="Скрыть обрыв выборки (4-е колено)" on={view.hideTrunc} onToggle={() => setView({ hideTrunc: !view.hideTrunc })} />
        <div className="text-xs leading-snug text-muted-foreground">
          Кластер в заглушке — связная компонента, отдельный фильтр «компонента» совпал бы с ним.
        </div>
      </div>

      <div className="flex flex-col gap-2.5 border-b border-border px-3.5 py-3">
        <div className={sectionTitle}>ОТОБРАЖЕНИЕ</div>
        <div className="flex items-center justify-between gap-2">
          <span className={rowLabel}>Направление</span>
          <Segmented
            options={[['arrows', 'Стрелки'], ['dash', 'Пунктир']]}
            value={view.flow}
            onChange={(flow) => setView({ flow })}
          />
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className={rowLabel}>Раскраска</span>
          <Segmented
            options={[['role', 'Роль'], ['cluster', 'Кластер']]}
            value={view.colorBy}
            onChange={(colorBy) => setView({ colorBy })}
          />
        </div>
        <Sliders items={DISPLAY_SLIDERS} />
      </div>

      <div className="flex flex-col gap-2.5 px-3.5 py-3">
        <div className={sectionTitle}>FORCES</div>
        <Sliders items={FORCE_SLIDERS} />
      </div>
    </div>
  )
}

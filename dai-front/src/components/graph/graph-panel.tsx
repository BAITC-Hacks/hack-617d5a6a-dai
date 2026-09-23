import { useQuery, useQueryClient, type Query } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { listClustersOptions } from '@/client/@tanstack/react-query.gen'
import type { NodeCard, TransferOut } from '@/client/types.gen'
import { createMoneyGraph, type MoneyGraph, type MoneyGraphData, type MoneyGraphViewState } from '@/components/graph/money-graph'
import { GraphSettings, Segmented } from '@/components/graph/graph-settings'
import { GraphTimeline } from '@/components/graph/graph-timeline'
import { getErrorMessage } from '@/lib/api-error'
import { count } from '@/lib/format'
import { errorKind, graphQuery, nodeQuery, topQuery, useNodeIndex } from '@/lib/graph-data'
import { cn } from '@/lib/utils'
import { useGraphView } from '@/stores/graph-view'

const NODE_KEY_ID = nodeQuery('').queryKey[0]._id
const isNodeQuery = (q: Query) => (q.queryKey[0] as { _id?: string } | undefined)?._id === NODE_KEY_ID

/** Переводы из всех загруженных карточек узлов (кеш TanStack Query), без повторов. Растёт по мере открытия карточек. */
function useLoadedTransfers() {
  const queryClient = useQueryClient()
  const [transfers, setTransfers] = useState<TransferOut[]>([])
  useEffect(() => {
    const cache = queryClient.getQueryCache()
    const collect = () => {
      const seen = new Map<string, TransferOut>()
      for (const q of cache.findAll({ predicate: isNodeQuery })) {
        for (const t of (q.state.data as NodeCard | undefined)?.transfers ?? []) seen.set(`${t.src}|${t.dst}|${t.date}|${t.sum_kzt}`, t)
      }
      // ponytail: сравниваем только размер — карточки из кеша не удаляются до перезагрузки (staleTime: Infinity)
      setTransfers((prev) => (prev.length === seen.size ? prev : [...seen.values()]))
    }
    collect()
    return cache.subscribe((e) => {
      if (e.type === 'updated' && e.action.type === 'success' && isNodeQuery(e.query)) collect()
    })
  }, [queryClient])
  return transfers
}

const toolBtn = 'h-[30px] cursor-pointer whitespace-nowrap rounded-lg border px-2.5 text-xs font-medium'

export function GraphPanel({ gid }: { gid: string | null }) {
  const navigate = useNavigate()
  const graphQ = useQuery(graphQuery())
  const topQ = useQuery(topQuery())
  const clustersQ = useQuery({ ...listClustersOptions(), meta: { silent: true } })
  const nodeQ = useQuery({ ...nodeQuery(gid ?? ''), enabled: !!gid })
  const transfers = useLoadedTransfers()

  const view = useGraphView((s) => s.view)
  const setView = useGraphView((s) => s.setView)
  const settingsOpen = useGraphView((s) => s.settingsOpen)
  const toggleSettings = useGraphView((s) => s.toggleSettings)
  const play = useGraphView((s) => s.play)
  const range = useGraphView((s) => s.range)

  // Фокус — выбранный gid, если он есть в загруженной сети или его карточка пришла; пока неизвестный gid грузится
  // или не нашёлся (404), граф держит прежний. Узел не выбран — фокуса нет.
  const index = useNodeIndex()
  const [focus, setFocus] = useState<string | null>(null)
  if (!gid && focus !== null) setFocus(null)
  if (gid && (index.has(gid) || nodeQ.isSuccess) && focus !== gid) setFocus(gid)

  // Открыли карточку (очередь, клик по графу, ссылка) — сразу показываем окружение узла.
  // Вручную переключить режим можно — он сменится только при выборе следующего узла.
  const prevGid = useRef<string | null>(null)
  useEffect(() => {
    if (gid === prevGid.current) return
    prevGid.current = gid
    if (gid) setView({ mode: 'local' })
  }, [gid, setView])

  // Один MoneyGraph на смонтированный контейнер; ref-cleanup React 19 уничтожает его при размонтировании.
  const [graph, setGraph] = useState<MoneyGraph | null>(null)
  const prevView = useRef<MoneyGraphViewState | null>(null)
  const navigateRef = useRef(navigate)
  useEffect(() => {
    navigateRef.current = navigate
  }, [navigate])
  const mount = useCallback((el: HTMLDivElement) => {
    const g = createMoneyGraph(el, { onSelect: (to) => void navigateRef.current({ to: '/nodes/$gid', params: { gid: to } }) })
    prevView.current = null
    setGraph(g)
    return () => {
      g.destroy()
      setGraph(null)
    }
  }, [])

  // Ждём /graph, /clusters и /top вместе, чтобы первая раскладка была одна. Позже setData сохраняет позиции узлов.
  const data = useMemo<MoneyGraphData | null>(() => {
    if (!graphQ.data || clustersQ.isPending || topQ.isPending) return null
    return {
      nodes: graphQ.data.nodes,
      edges: graphQ.data.edges,
      transfers,
      clusters: clustersQ.data?.items ?? [],
      top: topQ.data?.items.map((t) => t.gid) ?? [],
    }
  }, [graphQ.data, clustersQ.isPending, clustersQ.data, topQ.isPending, topQ.data, transfers])

  useEffect(() => {
    if (graph && data) graph.setData(data)
  }, [graph, data])

  const [counts, setCounts] = useState<{ n: number; e: number } | null>(null)
  useEffect(() => {
    if (!graph || !data) return
    if (!focus && view.mode === 'local' && !prevView.current) return
    const next: MoneyGraphViewState = { ...view, focus, play, range }
    const prev = prevView.current
    prevView.current = next
    const modeChanged = prev?.mode !== next.mode
    const focusChanged = prev?.focus !== next.focus
    graph.setView(next, { fit: (next.mode === 'local' && (focusChanged || modeChanged)) || (next.mode === 'overview' && modeChanged) })
    if (next.mode === 'overview' && focusChanged && !modeChanged && focus) graph.flyTo(focus)
    const c = graph.counts()
    setCounts((p) => (p && p.n === c.n && p.e === c.e ? p : c))
  }, [graph, data, view, focus, play, range])

  const nodeErr = gid ? errorKind(nodeQ.error) : null
  const isDown = nodeErr === 'down' || graphQ.isError
  const is404 = !isDown && nodeErr === 'notFound'
  const isLocal = view.mode === 'local'
  const isIsolated = nodeQ.isSuccess && isLocal && nodeQ.data.in_edges.length + nodeQ.data.out_edges.length === 0

  const retry = () => {
    if (gid) void nodeQ.refetch()
    if (!graphQ.data) void graphQ.refetch()
    if (topQ.isError) void topQ.refetch()
    if (clustersQ.isError) void clustersQ.refetch()
  }

  const dirChips: [string, boolean, () => void][] = [
    ['Откуда пришли деньги', view.dirIn, () => setView({ dirIn: !view.dirIn })],
    ['Куда ушли деньги', view.dirOut, () => setView({ dirOut: !view.dirOut })],
    ['Связи между соседями', view.between, () => setView({ between: !view.between })],
  ]

  return (
    <main className="dark relative flex min-h-0 min-w-0 flex-col bg-background text-foreground">
      <div className="flex flex-none flex-wrap items-center gap-x-2.5 gap-y-2 border-b border-border bg-card px-3 py-2">
        <Segmented
          options={[['local', 'Окружение узла'], ['overview', 'Общий вид']]}
          value={view.mode}
          onChange={(mode) => setView({ mode })}
        />
        {/* Строка окружения видна всегда (в общем виде неактивна): высота холста не меняется, граф не прыгает */}
        <fieldset
          disabled={!isLocal}
          title={isLocal ? undefined : 'Настройки окружения узла — в режиме «Окружение узла»'}
          className="order-3 flex basis-full flex-wrap items-center gap-2 transition-opacity disabled:opacity-40"
        >
          <label className="flex h-[30px] items-center gap-2 rounded-lg border border-border bg-muted px-2.5 text-xs font-medium whitespace-nowrap text-foreground/85">
            Глубина
            <input
              type="range"
              min={1}
              max={4}
              step={1}
              value={view.depth}
              onChange={(e) => setView({ depth: +e.target.value })}
              className="w-[70px] accent-foreground"
            />
            <span className="font-mono text-[13px] font-semibold text-foreground">{count(view.depth, 'хоп', 'хопа', 'хопов')}</span>
          </label>
          {dirChips.map(([label, on, toggle]) => (
            <button
              key={label}
              type="button"
              aria-pressed={on}
              onClick={toggle}
              className={cn(
                toolBtn,
                'flex items-center gap-1.5',
                on ? 'border-foreground/25 bg-muted text-foreground' : 'border-border text-muted-foreground',
              )}
            >
              <span
                className={cn(
                  'grid size-3 place-items-center rounded-[3px] border-[1.5px] border-current text-[9px] leading-none font-bold',
                  on && 'bg-foreground text-background',
                )}
              >
                {on && '✓'}
              </span>
              {label}
            </button>
          ))}
        </fieldset>
        <fieldset
          disabled={!isLocal}
          title="Раскладка окружения узла; выбор запоминается"
          className="order-1 transition-opacity disabled:opacity-40"
        >
          <Segmented
            options={[['force', 'Force'], ['layers', 'Слои']]}
            value={view.layout}
            onChange={(layout) => setView({ layout })}
          />
        </fieldset>
        <div className="order-2 ml-auto flex items-center gap-2">
          {counts && (
            <span className="text-xs whitespace-nowrap text-muted-foreground">
              {count(counts.n, 'узел', 'узла', 'узлов')} · {count(counts.e, 'связь', 'связи', 'связей')}
            </span>
          )}
          <button type="button" onClick={() => graph?.fit()} className={cn(toolBtn, 'border-border bg-muted hover:bg-accent')}>
            Вписать
          </button>
          <button
            type="button"
            aria-pressed={settingsOpen}
            onClick={toggleSettings}
            className={cn(toolBtn, settingsOpen ? 'border-foreground bg-foreground text-background' : 'border-border bg-muted hover:bg-accent')}
          >
            Настройки графа
          </button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        <div ref={mount} className="absolute inset-0" />

        {graphQ.isPending && (
          <div className="absolute inset-0 grid place-items-center bg-background text-[13.5px] font-medium text-muted-foreground">
            Загружаем сеть…
          </div>
        )}
        {is404 && (
          <div className="absolute inset-0 grid place-items-center bg-background/90">
            <div className="flex max-w-[420px] flex-col items-center gap-2.5 text-center">
              <div className="font-mono text-xs font-medium text-muted-foreground">404</div>
              <div className="text-[22px] font-semibold">{getErrorMessage(nodeQ.error)}</div>
              <div className="text-sm leading-normal text-foreground/80">
                Такого клиента нет в выгрузке. Проверьте gid: 18 цифр, начинается с 10000000.
              </div>
            </div>
          </div>
        )}
        {isDown && (
          <div className="absolute inset-0 grid place-items-center bg-background/90">
            <div className="flex max-w-[420px] flex-col items-center gap-3 text-center">
              <div className="grid size-10 place-items-center rounded-full border-2 border-foreground/90 text-lg font-bold">!</div>
              <div className="text-[22px] font-semibold">Сервер анализа недоступен</div>
              <div className="text-sm leading-normal text-foreground/80">
                Запрос не дошёл до сервера. Данные о клиенте не проверены — это не означает, что его нет в выгрузке.
              </div>
              <button
                type="button"
                onClick={retry}
                className="mt-1 h-[38px] cursor-pointer rounded-lg bg-foreground px-4.5 text-sm font-semibold text-background"
              >
                Повторить запрос
              </button>
            </div>
          </div>
        )}
        {isLocal && !gid && graphQ.isSuccess && (
          <div className="absolute inset-0 grid place-items-center">
            <div className="flex max-w-[380px] flex-col items-center gap-2 text-center">
              <div className="text-lg font-semibold">Узел не выбран</div>
              <div className="text-sm leading-normal text-foreground/75">
                Выберите клиента в очереди «Кого проверить первым», найдите по gid или кликните по узлу в «Общем виде».
              </div>
            </div>
          </div>
        )}
        {isIsolated && (
          <div className="absolute top-4 left-1/2 flex -translate-x-1/2 items-center gap-2.5 rounded-[10px] border border-border bg-muted px-3.5 py-2 whitespace-nowrap">
            <span className="text-sm font-semibold">Связей в выгрузке нет</span>
            <span className="text-[13.5px] text-foreground/80">клиент — seed, в результате он остаётся</span>
          </div>
        )}

        <div className="pointer-events-none absolute bottom-3 left-3 flex flex-col gap-1.5 rounded-[10px] border border-border bg-card/90 px-3 py-2.5 text-xs font-medium text-foreground/80">
          <div className="flex items-center gap-2">
            <span className="flex w-[34px] items-center gap-[3px]">
              <span className="size-[5px] rounded-full bg-muted-foreground" />
              <span className="size-3 rounded-full bg-muted-foreground" />
            </span>
            размер — приоритет проверки
          </div>
          <div className="flex items-center gap-2">
            <span className="flex w-[34px]">
              <span className="size-3 rounded-full border-2 border-foreground bg-muted-foreground/60" />
            </span>
            seed ·
            <span className="size-3 rounded-full border-[1.5px] border-dashed border-foreground/80 bg-muted-foreground/60" />
            граница выгрузки
          </div>
          <div className="flex items-center gap-2">
            <span className="flex w-[34px] items-center">
              <span className="h-0 flex-1 border-t-2 border-foreground/80" />
              <span className="size-0 border-y-[4px] border-l-[7px] border-y-transparent border-l-foreground/80" />
            </span>
            {view.flow === 'dash' ? 'стрелка — направление денег, у выбранного бежит пунктир' : 'стрелка — направление денег'}
          </div>
        </div>

        <span className="pointer-events-none absolute top-2.5 right-3 text-[11.5px] text-muted-foreground">
          Прокрутка — масштаб · Перетаскивание — движение · Клик — узел
        </span>
        <div className="absolute right-3 bottom-3">
          <div className="flex flex-col overflow-hidden rounded-lg border border-border bg-card/90">
            {(
              [
                ['+', 'Приблизить', () => graph?.zoomBy(1.35)],
                ['−', 'Отдалить', () => graph?.zoomBy(1 / 1.35)],
                ['⊡', 'Вписать граф', () => graph?.fit()],
              ] as const
            ).map(([icon, label, act]) => (
              <button
                key={label}
                type="button"
                aria-label={label}
                title={label}
                onClick={act}
                className="size-8 cursor-pointer border-b border-border text-base last:border-b-0 hover:bg-accent"
              >
                {icon}
              </button>
            ))}
          </div>
        </div>

        {settingsOpen && <GraphSettings />}
      </div>

      <GraphTimeline transfers={transfers} />
    </main>
  )
}

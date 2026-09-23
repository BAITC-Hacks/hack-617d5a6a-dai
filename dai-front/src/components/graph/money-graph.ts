import * as d3 from 'd3'
import type { ClusterOut, EdgeOut, NodeOut, TransferOut } from '@/client/types.gen'
import { formatInt, formatKztCompact, formatScore, gidParts } from '@/lib/format'
import { ROLE_FALLBACK_TITLE, roleVar } from '@/lib/roles'
import { DEFAULT_VIEW, type GraphView } from '@/stores/graph-view'

// Схема сети: D3 (force, zoom, drag) + SVG, порт design-outputs/money-graph.js (доработанный движок из макета Claude Design).
// Контракт между MoneyGraph (императивный D3) и GraphPanel (React). Реализация — ниже.

export type MoneyGraphData = {
  nodes: NodeOut[]
  edges: EdgeOut[]
  /** Переводы с датами — для таймлапса и диапазона дат; сейчас только из загруженных карточек узлов */
  transfers: TransferOut[]
  clusters: ClusterOut[]
  /** gid топ-20: их подписи видны всегда */
  top: string[]
}

export type MoneyGraphViewState = GraphView & {
  focus: string | null
  /** День июля 1–31 для таймлапса, null — выключен */
  play: number | null
  range: [number, number] | null
}

export type MoneyGraphCallbacks = {
  onSelect?: (gid: string) => void
  onBackground?: () => void
}

export type MoneyGraph = {
  /** Повторный вызов сохраняет позиции известных gid; раскладка пересчитывается, только если изменился состав узлов/рёбер */
  setData: (data: MoneyGraphData) => void
  setView: (view: MoneyGraphViewState, opts?: { fit?: boolean }) => void
  flyTo: (gid: string) => void
  hover: (gid: string | null) => void
  fit: () => void
  /** Приблизить (factor > 1) или отдалить (< 1) относительно центра */
  zoomBy: (factor: number) => void
  /** Сколько узлов и связей сейчас видно (без «призрачных» при таймлапсе) */
  counts: () => { n: number; e: number }
  destroy: () => void
}

// Собственная палитра рисунка графа (тёмный холст в духе graph view). Цвета ролей — токены темы через roleVar.
const MONO = 'var(--font-mono)'
const SANS = 'var(--font-sans)'
const BG = '#17171c'
const CL = ['#8ec5ff', '#ffb86b', '#b8e986', '#f5a3c7', '#c9b6ff', '#7fe0d4', '#ffd86b', '#ff9e9e']
const STUB = '#5a5a60'
const EDGE = '#777786'
const ORIGIN = { x: 0, y: 0 }
const NO_ROLE = 'роль не загружена'
let instance = 0

const dayOf = (d: string) => +d.slice(8, 10)
const LOG_MIN = Math.log(5000)
const LOG_SPAN = Math.log(4.4e6) - LOG_MIN
/** Толщина 1–8 по логарифму суммы ребра между 5 тыс. и 4,4 млн ₸ (DAI.edgeWidth из макета). */
const edgeWidth = (sum: number) => 1 + 7 * Math.min(1, Math.max(0, (Math.log(Math.max(sum, 5000)) - LOG_MIN) / LOG_SPAN))
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
const push = <K, V>(m: Map<K, V[]>, key: K, v: V) => {
  const list = m.get(key)
  if (list) list.push(v)
  else m.set(key, [v])
}

type GNode = d3.SimulationNodeDatum & {
  id: string
  /** Для узлов-заглушек (есть только в рёбрах) — только gid */
  n: Partial<NodeOut>
  stub: boolean
  x: number
  y: number
  deg: number
  layer: number
  ghost: boolean
  /** Цель и старт анимации послойной раскладки */
  tx: number
  ty: number
  sx: number
  sy: number
}

type GLink = {
  id: string
  source: GNode
  target: GNode
  e: EdgeOut
  first: number | null
  days: number[] | null
  recip: boolean
  ghost: boolean
  /** Ребро сейчас на экране — для соседей при наведении */
  vis: boolean
  index?: number
}

type Hull = [number, GNode[]]
type Box = { x: number; y: number; w: number; h: number }

// ponytail: SVG + переходы на каждом элементе — на обзоре ~2,2 тыс. узлов и ~3,1 тыс. рёбер это держит;
// если начнёт тормозить (наведение, таймлапс, drag на обзоре) — рёбра и узлы на Canvas, подписи и ореолы оставить в SVG.
export function createMoneyGraph(el: HTMLElement, cb: MoneyGraphCallbacks = {}): MoneyGraph {
  const uid = `dai-${++instance}`
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const duration = (ms: number) => (reduced ? 0 : ms)
  let destroyed = false

  const root = d3
    .select(el)
    .style('position', 'absolute')
    .style('inset', '0')
    .style('background', BG)
    .style('background-image', 'radial-gradient(ellipse at 50% 45%, #252334 0%, transparent 65%)')
    .style('overflow', 'hidden')
  const svg = root
    .append('svg')
    .attr('width', '100%')
    .attr('height', '100%')
    .style('display', 'block')
    .style('cursor', 'grab')
    .attr('aria-label', 'Интерактивный граф переводов')
    .attr('role', 'group')
  svg.append('style').text(
    '@keyframes daiDash{to{stroke-dashoffset:-20}}' +
      '.dai-flow{stroke-dasharray:6 4;animation:daiDash 1.4s linear infinite}' +
      '@keyframes daiSeed{0%,100%{stroke-opacity:1}50%{stroke-opacity:.35}}' +
      '.dai-seed{animation:daiSeed 1.8s ease-in-out 1}' +
      '.n:focus{outline:none}.n:focus .c{stroke:#fff;stroke-width:3}' +
      '@media(prefers-reduced-motion:reduce){.dai-flow,.dai-seed{animation:none}}',
  )
  const defs = svg.append('defs')
  const glow = defs.append('filter').attr('id', `${uid}-glow`).attr('x', '-100%').attr('y', '-100%').attr('width', '300%').attr('height', '300%')
  glow.append('feGaussianBlur').attr('stdDeviation', 3).attr('result', 'blur')
  const merge = glow.append('feMerge')
  merge.append('feMergeNode').attr('in', 'blur')
  merge.append('feMergeNode').attr('in', 'SourceGraphic')
  defs
    .append('marker')
    .attr('id', `${uid}-arr`)
    .attr('viewBox', '0 -4 8 8')
    .attr('refX', 7)
    .attr('refY', 0)
    .attr('markerWidth', 7)
    .attr('markerHeight', 7)
    .attr('markerUnits', 'userSpaceOnUse')
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-3.5L8,0L0,3.5')
    .attr('fill', '#9a9aa0')
  const g = svg.append('g')
  const gH = g.append('g')
  const gL = g.append('g')
  const gN = g.append('g')
  const gT = g.append('g')
  const gR = g.append('g')
  const tip = root
    .append('div')
    .style('position', 'absolute')
    .style('pointer-events', 'none')
    .style('display', 'none')
    .style('z-index', '5')
    .style('background', 'rgba(24,24,27,.96)')
    .style('border', '1px solid #3a3a40')
    .style('border-radius', '8px')
    .style('padding', '8px 10px')
    .style('color', '#ececf0')
    .style('font', `13px/1.4 ${SANS}`)
    .style('min-width', '220px')
    .style('box-shadow', '0 8px 28px rgba(0,0,0,.45)')

  let N = new Map<string, GNode>()
  let E: GLink[] = []
  // Смежность по всем рёбрам: обход окружения и соседи при наведении без прохода по всем рёбрам
  let outAdj = new Map<string, GLink[]>()
  let inAdj = new Map<string, GLink[]>()
  let passports = new Map<number, ClusterOut>()
  let top = new Set<string>()
  let V: MoneyGraphViewState = { ...DEFAULT_VIEW, focus: null, play: null, range: null }
  let vis: { nodes: GNode[]; edges: GLink[] } = { nodes: [], edges: [] }
  let hoverId: string | null = null
  let first = true
  /** Состав узлов/рёбер изменился после первой отрисовки: следующий setView перекладывает граф */
  let dirty = false
  let pendingFit = false
  let k = 1
  let camT: d3.Timer | null = null
  let layoutT: d3.Timer | null = null

  let linkSel = gL.selectAll<SVGPathElement, GLink>('path')
  let nodeSel = gN.selectAll<SVGGElement, GNode>('g.n')
  let textSel = gT.selectAll<SVGTextElement, GNode>('text')
  let hullSel = gH.selectAll<SVGGElement, Hull>('g.h')

  const zoom = d3
    .zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.15, 6])
    .on('zoom', (e: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
      g.attr('transform', e.transform.toString())
      k = e.transform.k
      labels(0)
    })
  svg.call(zoom).on('dblclick.zoom', null)

  // На больших графах кадр упирается в перерисовку SVG (~55 мс на 2,2 тыс. узлов), а не в физику (~10 мс):
  // считаем до 3 тиков на кадр, чтобы раскладка оседала за ~4 с, а не за ~11.
  const sim = d3
    .forceSimulation<GNode>()
    .alphaMin(0.02)
    .stop()
    .on('tick', () => {
      const extra = Math.min(2, Math.floor(sim.nodes().length / 1000))
      if (extra) sim.tick(extra)
      draw()
    })
    .on('end', () => {
      if (pendingFit) {
        pendingFit = false
        fit(500)
      }
    })

  function setData(d: MoneyGraphData) {
    // Объекты узлов и рёбер переиспользуются по gid/ключу: позиции, скорости и fx/fy сохраняются,
    // симуляция и таймеры раскладки продолжают работать с теми же объектами.
    const prevN = N
    const prevE = new Map(E.map((l) => [l.id, l]))
    let reused = 0
    const node = (gid: string, n: Partial<NodeOut>, stub: boolean) => {
      const o = prevN.get(gid)
      if (o) {
        reused++
        o.n = n
        o.stub = stub
        o.deg = 0
        N.set(gid, o)
      } else N.set(gid, { id: gid, n, stub, x: NaN, y: NaN, deg: 0, layer: 0, ghost: false, tx: NaN, ty: NaN, sx: NaN, sy: NaN })
    }
    N = new Map()
    E = []
    outAdj = new Map()
    inAdj = new Map()
    top = new Set(d.top)
    passports = new Map(d.clusters.map((c) => [c.cluster_id, c]))
    for (const n of d.nodes) node(n.gid, n, false)
    const firstDay = new Map<string, number>()
    const days = new Map<string, number[]>()
    for (const t of d.transfers) {
      const key = t.src + '|' + t.dst
      const dd = dayOf(t.date)
      firstDay.set(key, Math.min(firstDay.get(key) ?? 99, dd))
      push(days, key, dd)
    }
    const keys = new Set<string>()
    for (const e of d.edges) {
      for (const gid of [e.src, e.dst]) if (!N.has(gid)) node(gid, { gid }, true)
      const key = e.src + '|' + e.dst
      keys.add(key)
      const old = prevE.get(key)
      const l: GLink = old ?? { id: key, source: N.get(e.src)!, target: N.get(e.dst)!, e, first: null, days: null, recip: false, ghost: false, vis: false }
      if (old) reused++
      l.e = e
      l.first = firstDay.get(key) ?? null
      l.days = days.get(key) ?? null
      E.push(l)
      push(outAdj, e.src, l)
      push(inAdj, e.dst, l)
      l.source.deg++
      l.target.deg++
    }
    for (const l of E) l.recip = keys.has(l.e.dst + '|' + l.e.src)
    if (prevN.size === 0) first = true
    else if (reused !== prevN.size + prevE.size || N.size !== prevN.size || E.length !== prevE.size) dirty = true
  }

  const R = (o: GNode) => (o.n.priority_score == null ? 2.5 : 2.5 + 8 * o.n.priority_score) * V.nodeScale
  const color = (o: GNode) => {
    if (o.stub || !o.n.role) return STUB
    if (V.colorBy === 'cluster') return CL[(o.n.cluster_id || 0) % CL.length]
    return roleVar(o.n.role)
  }
  const ew = (l: GLink) => (0.5 + (2.2 * (edgeWidth(l.e.sum_kzt) - 1)) / 7) * V.edgeScale
  const usesSim = () => !(V.mode === 'local' && V.layout === 'layers')
  const roleTitle = (o: GNode) => (o.n.role ? ROLE_FALLBACK_TITLE[o.n.role] : NO_ROLE)

  // ---------- видимость ----------
  function compute() {
    let ids: Map<string, number>
    const focus = V.focus
    if (V.mode === 'local' && focus && N.has(focus)) {
      ids = new Map([[focus, 0]])
      const walk = (dir: 1 | -1) => {
        const adj = dir < 0 ? inAdj : outAdj
        let front = [focus]
        for (let d = 1; d <= V.depth; d++) {
          const nx: string[] = []
          for (const a of front) {
            for (const l of adj.get(a) ?? []) {
              const b = dir < 0 ? l.source.id : l.target.id
              if (!ids.has(b)) {
                ids.set(b, dir * d)
                nx.push(b)
              }
            }
          }
          front = nx
        }
      }
      if (V.dirIn) walk(-1)
      if (V.dirOut) walk(1)
    } else if (V.mode === 'local') {
      ids = new Map()
    } else {
      ids = new Map()
      for (const id of N.keys()) ids.set(id, 0)
    }
    const pass = (o: GNode) => {
      if (o.id === V.focus) return true
      if (V.roles && o.n.role && !V.roles.includes(o.n.role)) return false
      if (V.clusters && o.n.cluster_id != null && !V.clusters.includes(o.n.cluster_id)) return false
      if (V.hideTrunc && o.n.truncated_by_depth) return false
      if (!V.showIsolated && o.n.is_seed && o.deg === 0) return false
      return true
    }
    const nodes = [...ids.keys()].map((id) => N.get(id)!).filter(pass)
    for (const o of nodes) o.layer = ids.get(o.id)!
    const S = new Set(nodes.map((o) => o.id))
    let edges = E.filter((l) => S.has(l.source.id) && S.has(l.target.id))
    if (V.mode === 'local' && !V.between) {
      edges = edges.filter((l) => {
        const a = l.source.layer
        const b = l.target.layer
        return b === a + 1 && (a >= 0 || b <= 0)
      })
    }
    // даты: диапазон и таймлапс
    const timed = V.play != null || !!V.range
    for (const l of edges) {
      let on = true
      if (V.range && l.days) {
        const [from, to] = V.range
        on = l.days.some((d) => d >= from && d <= to)
      }
      if (V.play != null && l.first) on = on && l.first <= V.play
      l.ghost = !on || (timed && !l.days)
    }
    const grown = new Set<string>()
    for (const l of edges) {
      if (!l.ghost) {
        grown.add(l.source.id)
        grown.add(l.target.id)
      }
    }
    for (const o of nodes) o.ghost = timed && !grown.has(o.id) && !o.n.is_seed && o.id !== V.focus
    for (const l of E) l.vis = false
    for (const l of edges) l.vis = true
    vis = { nodes, edges }
  }

  // ---------- раскладки ----------
  function clusterCenters(nodes: GNode[]) {
    const by = d3.rollup(
      nodes,
      (v) => v.length,
      (o) => o.n.cluster_id ?? -1,
    )
    const ids = [...by.keys()].sort((a, b) => by.get(b)! - by.get(a)!)
    const C = new Map<number, { x: number; y: number }>()
    ids.forEach((id, i) => {
      if (i === 0) {
        C.set(id, ORIGIN)
        return
      }
      const a = i * 2.4
      const r = 150 + 34 * Math.sqrt(i) * 3
      C.set(id, { x: r * Math.cos(a), y: r * Math.sin(a) })
    })
    return C
  }

  function layers(nodes: GNode[], edges: GLink[]) {
    const T = new Map<string, { x: number; y: number }>()
    const sumTo = new Map<string, number>()
    for (const l of edges) {
      sumTo.set(l.source.id, (sumTo.get(l.source.id) || 0) + l.e.sum_kzt)
      sumTo.set(l.target.id, (sumTo.get(l.target.id) || 0) + l.e.sum_kzt)
    }
    d3.group(nodes, (o) => o.layer).forEach((list, L) => {
      list.sort((a, b) => (sumTo.get(b.id) || 0) - (sumTo.get(a.id) || 0))
      const per = list.length > 30 ? 22 : 12
      list.forEach((o, i) => {
        const c = Math.floor(i / per)
        const row = i % per
        const inCol = Math.min(per, list.length - c * per)
        const dir = L < 0 ? -1 : 1
        T.set(o.id, { x: L * 210 + dir * c * 58 * (L === 0 ? 0 : 1), y: (row - (inCol - 1) / 2) * 30 })
      })
    })
    return T
  }

  function place(animate: boolean) {
    const { nodes, edges } = vis
    sim.stop()
    layoutT?.stop()
    layoutT = null
    animate = animate && !reduced
    if (!usesSim()) {
      const T = layers(nodes, edges)
      for (const o of nodes) {
        o.fx = null
        o.fy = null
        const t = T.get(o.id)!
        o.tx = t.x
        o.ty = t.y
        if (isNaN(o.x)) {
          o.x = 0
          o.y = 0
        }
        o.sx = o.x
        o.sy = o.y
      }
      if (!animate) {
        for (const o of nodes) {
          o.x = o.tx
          o.y = o.ty
        }
        draw()
        return
      }
      const t0 = performance.now()
      const tm = d3.timer(() => {
        const p = Math.min(1, (performance.now() - t0) / 700)
        const e = d3.easeCubicInOut(p)
        for (const o of nodes) {
          o.x = o.sx + (o.tx - o.sx) * e
          o.y = o.sy + (o.ty - o.sy) * e
        }
        draw()
        if (p >= 1) {
          tm.stop()
          layoutT = null
        }
      })
      layoutT = tm
      return
    }
    const C = V.mode === 'overview' ? clusterCenters(nodes) : null
    const center = (o: GNode) => (C ? C.get(o.n.cluster_id ?? -1)! : ORIGIN)
    const fresh = nodes.filter((o) => isNaN(o.x))
    for (const o of fresh) {
      const c = center(o)
      o.x = c.x + (Math.random() - 0.5) * 60
      o.y = c.y + (Math.random() - 0.5) * 60
    }
    for (const o of nodes) {
      o.fx = V.mode === 'local' && o.id === V.focus ? 0 : null
      o.fy = o.fx
    }
    const pull = C ? V.clusterPull : 0.04
    sim
      .nodes(nodes)
      .force('charge', d3.forceManyBody<GNode>().strength(-V.charge).distanceMax(400))
      .force(
        'link',
        d3
          .forceLink<GNode, GLink>(edges)
          .id((o) => o.id)
          .distance(V.linkDist)
          .strength(0.6),
      )
      .force(
        'collide',
        d3.forceCollide<GNode>((o) => R(o) + 2),
      )
      .force('cx', d3.forceX<GNode>((o) => center(o).x).strength(pull))
      .force('cy', d3.forceY<GNode>((o) => center(o).y).strength(pull))
    // Почти всё новое — часть раскладки досчитываем синхронно, остаток доигрывается анимацией
    if (fresh.length > nodes.length * 0.5) {
      sim.alpha(1)
      for (let i = 0; i < (reduced ? 240 : 55); i++) sim.tick()
      draw()
      if (!reduced) sim.alpha(0.45).restart()
    } else if (reduced) {
      sim.alpha(0.5)
      for (let i = 0; i < 180; i++) sim.tick()
      draw()
    } else sim.alpha(animate ? 0.5 : 0.3).restart()
  }

  // ---------- отрисовка ----------
  function render(animate: boolean) {
    const dur = duration(animate ? 350 : 0)
    linkSel = gL
      .selectAll<SVGPathElement, GLink>('path')
      .data(vis.edges, (l) => l.id)
      .join(
        (en) => en.append('path').attr('fill', 'none').attr('stroke-opacity', 0).style('stroke', EDGE),
        (up) => up,
        (ex) => ex.transition().duration(dur).attr('stroke-opacity', 0).remove(),
      )
      .attr('stroke-width', ew)
      .attr('marker-end', V.flow === 'arrows' ? `url(#${uid}-arr)` : null)
    nodeSel = gN
      .selectAll<SVGGElement, GNode>('g.n')
      .data(vis.nodes, (o) => o.id)
      .join(
        (en) => {
          const s = en.append('g').attr('class', 'n').style('cursor', 'pointer').attr('opacity', 0)
          s.append('circle').attr('class', 'c')
          return s
        },
        (up) => up,
        (ex) => ex.transition().duration(dur).attr('opacity', 0).remove(),
      )
    nodeSel
      .attr('tabindex', 0)
      .attr('role', 'button')
      .attr('aria-label', (o) => `${o.id}, ${roleTitle(o)}`)
      .on('keydown', (e: KeyboardEvent, o) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          cb.onSelect?.(o.id)
        }
      })
      .on('focus', (_e, o) => hover(o.id))
      .on('blur', () => hover(null))
    nodeSel
      .select<SVGCircleElement>('circle.c')
      .attr('r', R)
      .style('fill', color)
      .attr('stroke', (o) => (o.n.is_seed ? '#ffffff' : o.n.truncated_by_depth ? '#d4d4d8' : BG))
      .attr('stroke-width', (o) => (o.n.is_seed ? 2 : o.n.truncated_by_depth ? 1.4 : 0.8))
      .attr('stroke-dasharray', (o) => (o.n.truncated_by_depth ? '2.5 2' : null))
      .attr('class', (o) => 'c' + (o.n.is_seed ? ' dai-seed' : ''))
    nodeSel.selectAll('circle.f').remove()
    nodeSel
      .filter((o) => o.id === V.focus)
      .insert('circle', 'circle.c')
      .attr('class', 'f')
      .attr('r', (o) => R(o) + 6)
      .attr('fill', 'none')
      .attr('stroke', '#ffffff')
      .attr('stroke-opacity', 0.55)
      .attr('stroke-width', 1.5)
    nodeSel
      .on('mouseenter', (e: MouseEvent, o) => hover(o.id, e))
      .on('mousemove', (e: MouseEvent) => moveTip(e))
      .on('mouseleave', () => hover(null))
      .on('click', (e: MouseEvent, o) => {
        e.stopPropagation()
        cb.onSelect?.(o.id)
      })
    nodeSel.call(
      d3
        .drag<SVGGElement, GNode>()
        .on('start', (_e, o) => {
          svg.style('cursor', 'grabbing')
          if (usesSim()) sim.alphaTarget(0.25).restart()
          o.fx = o.x
          o.fy = o.y
        })
        .on('drag', (e: d3.D3DragEvent<SVGGElement, GNode, GNode>, o) => {
          o.fx = e.x
          o.fy = e.y
          if (!usesSim()) {
            o.x = e.x
            o.y = e.y
            draw()
          }
        })
        .on('end', (_e, o) => {
          svg.style('cursor', 'grab')
          if (usesSim()) sim.alphaTarget(0)
          if (!(V.mode === 'local' && o.id === V.focus && usesSim())) {
            o.fx = null
            o.fy = null
          }
        }),
    )
    textSel = gT
      .selectAll<SVGTextElement, GNode>('text')
      .data(vis.nodes, (o) => o.id)
      .join(
        (en) =>
          en
            .append('text')
            .attr('opacity', 0)
            .attr('text-anchor', 'middle')
            .style('font-family', MONO)
            .attr('font-weight', 500)
            .style('pointer-events', 'none')
            .style('paint-order', 'stroke')
            .attr('stroke', BG)
            .attr('stroke-width', 3),
        (up) => up,
        (ex) => ex.remove(),
      )
      .text((o) => gidParts(o.id).mid)
      .attr('fill', (o) => (o.id === V.focus ? '#ffffff' : '#b4b4bc'))
    hulls(animate)
    opac(animate ? 400 : 0)
    labels(animate ? 300 : 0)
    flows()
    draw()
  }

  function hulls(animate: boolean) {
    const groups: Hull[] =
      V.mode === 'overview'
        ? [
            ...d3.group(
              vis.nodes.filter((o) => !o.ghost && o.n.cluster_id != null),
              (o) => o.n.cluster_id as number,
            ),
          ]
        : []
    hullSel = gH
      .selectAll<SVGGElement, Hull>('g.h')
      .data(groups, (d) => d[0])
      .join(
        (en) => {
          const s = en.append('g').attr('class', 'h').attr('opacity', 0)
          s.append('path')
          s.append('text')
            .attr('text-anchor', 'middle')
            .style('font-family', SANS)
            .attr('font-size', 12)
            .attr('font-weight', 500)
            .attr('fill', '#a1a1aa')
          return s
        },
        (up) => up,
        (ex) => ex.transition().duration(duration(300)).attr('opacity', 0).remove(),
      )
    hullSel
      .transition()
      .duration(duration(animate ? 400 : 0))
      .attr('opacity', 1)
    const hc = (d: Hull) => (V.colorBy === 'cluster' ? CL[d[0] % CL.length] : '#ffffff')
    hullSel.select('path').attr('fill', hc).attr('fill-opacity', 0.025).attr('stroke', hc).attr('stroke-opacity', 0.08)
    hullSel.select('text').text((d) => {
      const p = passports.get(d[0])
      return `Кластер ${d[0]} · ${formatInt(d[1].length)}${p ? ` из ${formatInt(p.n_nodes)}` : ''} узлов`
    })
  }

  const hullLine = d3.line().curve(d3.curveCatmullRomClosed.alpha(0.6))
  function drawHulls() {
    hullSel.each(function (d) {
      const pts: [number, number][] = []
      for (const o of d[1]) {
        const r = R(o) + 14
        for (let a = 0; a < 8; a++) pts.push([o.x + r * Math.cos((a * Math.PI) / 4), o.y + r * Math.sin((a * Math.PI) / 4)])
      }
      const h = d3.polygonHull(pts)
      if (!h) return
      const s = d3.select(this)
      s.select('path').attr('d', hullLine(h))
      s.select('text')
        .attr('x', d3.mean(d[1], (o) => o.x) ?? 0)
        .attr('y', (d3.min(h, (p) => p[1]) ?? 0) - 8)
    })
  }

  function path(l: GLink) {
    const s = l.source
    const t = l.target
    const dx = t.x - s.x
    const dy = t.y - s.y
    const len = Math.hypot(dx, dy) || 1
    const rt = R(t) + (V.flow === 'arrows' ? 2 : 0)
    const ux = dx / len
    const uy = dy / len
    const ex = t.x - ux * rt
    const ey = t.y - uy * rt
    if (!l.recip) return `M${s.x},${s.y}L${ex},${ey}`
    const off = Math.min(28, len * 0.18)
    const mx = (s.x + t.x) / 2 - uy * off
    const my = (s.y + t.y) / 2 + ux * off
    return `M${s.x},${s.y}Q${mx},${my} ${ex},${ey}`
  }

  function draw() {
    linkSel.attr('d', path)
    nodeSel.attr('transform', (o) => `translate(${o.x},${o.y})`)
    drawHulls()
    labels(0)
  }

  // ---------- состояние подсветки ----------
  function nb(id: string) {
    const s = new Set([id])
    for (const l of outAdj.get(id) ?? []) if (l.vis) s.add(l.target.id)
    for (const l of inAdj.get(id) ?? []) if (l.vis) s.add(l.source.id)
    return s
  }

  function opac(ms: number) {
    const dur = duration(ms)
    nodeSel.select('circle.c').attr('filter', (o) => (o.id === hoverId || o.id === V.focus ? `url(#${uid}-glow)` : null))
    const H = hoverId ? nb(hoverId) : null
    const hot = (l: GLink) => l.source.id === hoverId || l.target.id === hoverId
    nodeSel
      .transition()
      .duration(dur)
      .attr('opacity', (o) => (o.ghost ? 0.07 : 1) * (H ? (H.has(o.id) ? 1 : 0.12) : 1))
    linkSel
      .transition()
      .duration(dur)
      .attr('stroke-opacity', (l) => {
        if (l.ghost) return 0.03
        if (H) return hot(l) ? 0.95 : 0.04
        if (V.focus && (l.source.id === V.focus || l.target.id === V.focus)) return 0.7
        return 0.32
      })
      // style, а не attr: цвет роли — CSS-переменная
      .style('stroke', (l) => (H && hot(l) ? color(l.source) : EDGE))
    hullSel
      .transition()
      .duration(dur)
      .attr('opacity', H ? 0.35 : 1)
  }

  // Подписи: размер на экране не больше 12px (выбранный — 14px), пересекающиеся гасятся жадно по рангу
  // (наведённый > выбранный > приоритет). Сетка вместо попарной проверки — вызывается на каждом тике и зуме.
  function labels(ms: number) {
    const dur = duration(ms)
    const H = hoverId ? nb(hoverId) : null
    const fontSize = (o: GNode) => Math.min(o.id === V.focus ? 12 : 10, (o.id === V.focus ? 14 : 12) / k)
    const off = Math.min(12, 14 / k)
    hullSel.select('text').attr('font-size', Math.min(12, 12 / k))
    const few = V.mode === 'local' && vis.nodes.length <= 30
    const important = (o: GNode) => o.id === hoverId || o.id === V.focus
    const ranked = vis.nodes
      .filter((o) => !o.ghost && (important(o) || (H ? H.has(o.id) : top.has(o.id) || k >= V.labelZoom || few)))
      .sort(
        (a, b) =>
          Number(b.id === hoverId) - Number(a.id === hoverId) ||
          Number(b.id === V.focus) - Number(a.id === V.focus) ||
          (b.n.priority_score || 0) - (a.n.priority_score || 0),
      )
    const shown = new Set<string>()
    const cw = 80 / k
    const ch = 20 / k
    const grid = new Map<string, Box[]>()
    const hits = (a: Box, b: Box) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
    for (const o of ranked) {
      const font = fontSize(o)
      const pad = 6 / k
      const w = gidParts(o.id).mid.length * font * 0.65 + pad * 2
      const box = { x: o.x - w / 2, y: o.y + R(o) + off - font - pad / 2, w, h: font + pad }
      const cells: string[] = []
      for (let i = Math.floor(box.x / cw); i <= Math.floor((box.x + box.w) / cw); i++)
        for (let j = Math.floor(box.y / ch); j <= Math.floor((box.y + box.h) / ch); j++) cells.push(`${i},${j}`)
      if (important(o) || !cells.some((c) => grid.get(c)?.some((b) => hits(box, b)))) {
        shown.add(o.id)
        for (const c of cells) push(grid, c, box)
      }
    }
    // Двигаем и масштабируем только видимые подписи: перекладка тысяч скрытых <text> на каждом тике стоит ~20 мс
    textSel
      .filter((o) => shown.has(o.id))
      .attr('x', (o) => o.x)
      .attr('y', (o) => o.y + R(o) + off)
      .attr('font-size', fontSize)
      .attr('stroke-width', Math.min(3, 3 / k))
    const op = (o: GNode) => (shown.has(o.id) ? 1 : 0)
    if (dur) textSel.interrupt().transition().duration(dur).attr('opacity', op)
    else textSel.interrupt().attr('opacity', op)
  }

  function flows() {
    linkSel.classed('dai-flow', (l) => {
      if (reduced || V.flow !== 'dash' || l.ghost) return false
      if (hoverId) return l.source.id === hoverId || l.target.id === hoverId
      if (V.mode === 'local') return true
      return !!V.focus && (l.source.id === V.focus || l.target.id === V.focus)
    })
  }

  function hover(id: string | null, ev?: MouseEvent) {
    const o = id ? N.get(id) : undefined
    if (id && !o) return
    hoverId = id
    opac(150)
    labels(150)
    flows()
    if (!o) {
      tip.style('display', 'none')
      return
    }
    const n = o.n
    const row = (a: string, b: string) =>
      `<div style="display:flex;gap:14px;justify-content:space-between;white-space:nowrap"><span style="color:#a1a1aa">${a}</span><span style="font-family:${MONO}">${b}</span></div>`
    tip.html(
      `<div style="font:600 13px ${MONO};margin-bottom:4px">${esc(o.id)}</div>` +
        `<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span style="width:9px;height:9px;border-radius:50%;background:${n.role ? roleVar(n.role) : STUB}"></span>` +
        roleTitle(o) +
        (n.is_seed ? ' · seed' : '') +
        (n.truncated_by_depth ? ' · граница выгрузки' : '') +
        '</div>' +
        (n.priority_score != null ? row('приоритет', formatScore(n.priority_score)) : '') +
        (n.in_kzt != null ? row('вход', `${formatKztCompact(n.in_kzt)} · ${n.in_deg} отпр.`) : '') +
        (n.out_kzt != null
          ? row('выход', n.truncated_by_depth ? 'не выгружены' : `${formatKztCompact(n.out_kzt)} · ${n.out_deg} получ.`)
          : ''),
    )
    tip.style('display', 'block')
    if (ev) moveTip(ev)
    else {
      const t = d3.zoomTransform(svg.node()!)
      placeTip(t.applyX(o.x), t.applyY(o.y))
    }
  }
  function moveTip(e: MouseEvent) {
    const [x, y] = d3.pointer(e, el)
    placeTip(x, y)
  }
  function placeTip(x: number, y: number) {
    const box = tip.node()!.getBoundingClientRect()
    tip
      .style('left', `${Math.max(8, Math.min(x + 14, el.clientWidth - box.width - 8))}px`)
      .style('top', `${Math.max(8, Math.min(y + 14, el.clientHeight - box.height - 8))}px`)
  }

  // ---------- камера ----------
  function fit(ms = 600) {
    const lay = !usesSim()
    const px = (o: GNode) => (lay && !isNaN(o.tx) ? o.tx : o.x)
    const py = (o: GNode) => (lay && !isNaN(o.ty) ? o.ty : o.y)
    const ns = vis.nodes.filter((o) => !isNaN(px(o)))
    if (!ns.length) return
    const W = el.clientWidth || 600
    const H = el.clientHeight || 500
    const x0 = d3.min(ns, px)! - 40
    const x1 = d3.max(ns, px)! + 40
    const y0 = d3.min(ns, py)! - 50
    const y1 = d3.max(ns, py)! + 40
    const Hh = H - 70
    const s = Math.min(2.2, 0.94 * Math.min(W / (x1 - x0), Hh / (y1 - y0)))
    cam(d3.zoomIdentity.translate(W / 2 - (s * (x0 + x1)) / 2, Hh / 2 - (s * (y0 + y1)) / 2).scale(s), ms)
  }

  function cam(t1: d3.ZoomTransform, ms: number, done?: () => void) {
    const dur = duration(ms)
    camT?.stop()
    camT = null
    if (!dur) {
      svg.call(zoom.transform, t1)
      done?.()
      return
    }
    const t0 = d3.zoomTransform(svg.node()!)
    const ip = d3.interpolate([t0.x, t0.y, t0.k], [t1.x, t1.y, t1.k])
    const st = performance.now()
    const tm = d3.timer(() => {
      const p = Math.min(1, (performance.now() - st) / dur)
      const v = ip(d3.easeCubicInOut(p))
      svg.call(zoom.transform, d3.zoomIdentity.translate(v[0], v[1]).scale(v[2]))
      if (p >= 1) {
        tm.stop()
        camT = null
        done?.()
      }
    })
    camT = tm
  }

  function flyTo(id: string) {
    const o = N.get(id)
    if (!o || isNaN(o.x)) return
    const W = el.clientWidth || 600
    const H = el.clientHeight || 500
    const s = Math.max(k, 1.8)
    cam(d3.zoomIdentity.translate(W / 2 - s * o.x, H / 2 - s * o.y).scale(s), 750, () => pulse(o))
  }

  function pulse(o: GNode) {
    if (reduced || destroyed) return
    const c = gR.append('circle').attr('cx', o.x).attr('cy', o.y).attr('r', R(o)).attr('fill', 'none').attr('stroke', '#ffffff').attr('stroke-width', 2)
    const rep = (i: number) => {
      c.attr('r', R(o))
        .attr('stroke-opacity', 0.9)
        .transition()
        .duration(900)
        .ease(d3.easeCubicOut)
        .attr('r', R(o) + 34)
        .attr('stroke-opacity', 0)
        .on('end', () => (i < 2 ? rep(i + 1) : c.remove()))
    }
    rep(0)
  }

  const layoutKey = (v: MoneyGraphViewState) =>
    [v.mode, v.focus, v.depth, v.dirIn, v.dirOut, v.between, v.layout, v.roles, v.clusters, v.showIsolated, v.hideTrunc].join('|')
  const forceKey = (v: MoneyGraphViewState) => [v.charge, v.linkDist, v.clusterPull, v.nodeScale].join('|')

  function setView(nv: MoneyGraphViewState, opts?: { fit?: boolean }) {
    if (destroyed) return
    const prev = V
    V = { ...V, ...nv }
    compute()
    const relayout = first || dirty || layoutKey(prev) !== layoutKey(V) || forceKey(prev) !== forceKey(V)
    dirty = false
    // Сначала раскладка, потом отрисовка: иначе новые узлы рисуются с NaN-координатами (в макете было наоборот)
    if (relayout) place(!first)
    render(!first)
    if (relayout && (first || opts?.fit)) {
      fit(first ? 0 : 600)
      // при reduced motion раскладка уже досчитана синхронно, симуляция не запускается
      if (usesSim() && !reduced) pendingFit = true
    }
    if (first) {
      nodeSel.attr('opacity', 0)
      opac(700)
      first = false
    }
  }

  const resize = new ResizeObserver(() => {
    if (!first && !destroyed) fit(0)
  })
  resize.observe(el)
  svg.on('click', () => cb.onBackground?.())

  return {
    setData,
    setView,
    flyTo,
    hover: (id) => hover(id),
    fit: () => fit(600),
    zoomBy: (factor) => {
      svg.transition().duration(duration(250)).call(zoom.scaleBy, factor)
    },
    counts: () => ({ n: vis.nodes.filter((o) => !o.ghost).length, e: vis.edges.filter((l) => !l.ghost).length }),
    destroy: () => {
      destroyed = true
      resize.disconnect()
      camT?.stop()
      layoutT?.stop()
      sim.stop()
      root.selectAll('*').interrupt().remove()
    },
  }
}

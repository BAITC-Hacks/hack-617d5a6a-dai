import { create } from 'zustand'
import type { Role } from '@/lib/roles'

/** Что подсвечено из легенды: роль, seed или граница выгрузки. Остальные узлы серые, но остаются на месте. */
export type Highlight = Role | 'seed' | 'boundary'

/** Настройки схемы сети. Меняются тулбаром и панелью «Настройки графа», читаются MoneyGraph. */
export type GraphView = {
  highlight: Highlight | null
  mode: 'local' | 'overview'
  /** Окружение узла: сколько хопов от выбранного, 1–4 */
  depth: number
  dirIn: boolean
  dirOut: boolean
  /** Показывать связи между соседями, а не только дерево от выбранного */
  between: boolean
  layout: 'layers' | 'force'
  colorBy: 'role' | 'cluster'
  /** null — все роли */
  roles: Role[] | null
  /** null — все кластеры */
  clusters: number[] | null
  showIsolated: boolean
  hideTrunc: boolean
  flow: 'dash' | 'arrows'
  labelZoom: number
  nodeScale: number
  edgeScale: number
  charge: number
  linkDist: number
  clusterPull: number
}

// Раскладку окружения аналитик выбирает один раз — помним её между сессиями (по умолчанию Force).
const LAYOUT_KEY = 'dai.graph.layout'
function savedLayout(): GraphView['layout'] {
  try {
    return localStorage.getItem(LAYOUT_KEY) === 'layers' ? 'layers' : 'force'
  } catch {
    return 'force'
  }
}

export const DEFAULT_VIEW: GraphView = {
  highlight: null,
  mode: 'overview',
  depth: 1,
  dirIn: true,
  dirOut: true,
  between: true,
  layout: savedLayout(),
  colorBy: 'role',
  roles: null,
  clusters: null,
  showIsolated: true,
  hideTrunc: false,
  // Стрелки на рёбрах есть всегда; 'dash' добавляет бегущий пунктир у выбранных связей. При «уменьшить движение» — без него.
  flow: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'arrows' : 'dash',
  labelZoom: 1.6,
  nodeScale: 1,
  edgeScale: 1,
  charge: 60,
  linkDist: 40,
  clusterPull: 0.2,
}

// Только состояние просмотра. Узлы, рёбра и карточки — в TanStack Query; выбранный gid — в URL.
type GraphViewState = {
  view: GraphView
  settingsOpen: boolean
  /** Таймлапс: день июля 1–31, до которого показаны связи; null — выключен */
  play: number | null
  playing: boolean
  /** Выбранный на гистограмме диапазон дней [от, до]; null — весь июль */
  range: [number, number] | null
  setView: (patch: Partial<GraphView>) => void
  toggleSettings: () => void
  setPlay: (play: number | null, playing?: boolean) => void
  setRange: (range: [number, number] | null) => void
  resetTimeline: () => void
}

export const useGraphView = create<GraphViewState>()((set) => ({
  view: DEFAULT_VIEW,
  settingsOpen: false,
  play: null,
  playing: false,
  range: null,
  setView: (patch) => {
    if (patch.layout) {
      try {
        localStorage.setItem(LAYOUT_KEY, patch.layout)
      } catch {
        // приватный режим или запрет хранилища — просто не запоминаем
      }
    }
    set((s) => ({ view: { ...s.view, ...patch } }))
  },
  toggleSettings: () => set((s) => ({ settingsOpen: !s.settingsOpen })),
  setPlay: (play, playing = false) => set({ play, playing, range: null }),
  setRange: (range) => set({ range, play: null, playing: false }),
  resetTimeline: () => set({ play: null, playing: false, range: null }),
}))

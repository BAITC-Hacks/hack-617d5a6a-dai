import { create } from 'zustand'
import type { NodeOut } from '@/client/types.gen'

type Role = NodeOut['role']

// Только состояние просмотра. Узлы, рёбра и карточки — в TanStack Query; выбранный gid и radius — в URL.
type GraphViewState = {
  /** Узел под курсором: подсвечивается сразу на графе, в топ-листе и в карточке */
  hoveredGid: string | null
  /** Роли, скрытые кликом по легенде */
  hiddenRoles: Role[]
  setHovered: (gid: string | null) => void
  toggleRole: (role: Role) => void
}

export const useGraphView = create<GraphViewState>()((set) => ({
  hoveredGid: null,
  hiddenRoles: [],
  setHovered: (gid) => set({ hoveredGid: gid }),
  toggleRole: (role) =>
    set((s) => ({
      hiddenRoles: s.hiddenRoles.includes(role)
        ? s.hiddenRoles.filter((r) => r !== role)
        : [...s.hiddenRoles, role],
    })),
}))

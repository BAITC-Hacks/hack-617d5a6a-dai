import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getGraphOptions, getMetaOptions, getNodeOptions, getTopNodesOptions } from '@/client/@tanstack/react-query.gen'
import type { NodeOut } from '@/client/types.gen'
import { BackendUnavailableError } from '@/lib/api-error'
import { ROLE_FALLBACK_TITLE, type Role } from '@/lib/roles'

// Общие запросы экрана «Узел». Один ключ — один запрос: TanStack Query дедуплицирует их между колонками.
// silent: ошибки показывает сам экран (оверлей графа, карточка), без глобального тоста.

/** Вся сеть целиком (~1,2 МБ, 2 248 узлов): окружение узла и общий вид считаются на клиенте. */
export const graphQuery = () => ({ ...getGraphOptions({ query: { limit: 5000 } }), meta: { silent: true } })
export const metaQuery = () => ({ ...getMetaOptions(), meta: { silent: true } })
export const topQuery = () => ({ ...getTopNodesOptions({ query: { limit: 20 } }), meta: { silent: true } })
export const nodeQuery = (gid: string) => ({ ...getNodeOptions({ path: { gid } }), meta: { silent: true } })

/** gid → узел из /graph. Пустая Map, пока граф грузится. */
export function useNodeIndex() {
  const { data } = useQuery(graphQuery())
  return useMemo(() => new Map<string, NodeOut>((data?.nodes ?? []).map((n) => [n.gid, n])), [data])
}

/** Очередь проверки: узлы с in_queue из /graph по убыванию priority_score (/top отдаёт только 50). Номер в очереди = индекс + 1. */
export function useQueue() {
  const { data, isPending, error } = useQuery(graphQuery())
  const queue = useMemo(
    () => (data?.nodes ?? []).filter((n) => n.in_queue).sort((a, b) => b.priority_score - a.priority_score),
    [data],
  )
  return { queue, isPending, error }
}

/** Подпись и описание роли из /meta (запасная подпись — пока /meta не пришёл). */
export function useRoleInfo() {
  const { data } = useQuery(metaQuery())
  return useMemo(() => {
    const byRole = new Map((data?.roles ?? []).map((r) => [r.role, r]))
    return (role: Role | null | undefined) => {
      if (!role) return { title: 'роль не загружена', description: '' }
      const r = byRole.get(role)
      return { title: r?.title ?? ROLE_FALLBACK_TITLE[role], description: r?.description ?? '' }
    }
  }, [data])
}

/** Состояние ошибки запроса для экрана: «не найдено» (404 с detail) отдельно от «сервер недоступен». */
export function errorKind(error: unknown): 'down' | 'notFound' | null {
  if (!error) return null
  return error instanceof BackendUnavailableError ? 'down' : 'notFound'
}

import { useSuspenseQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { getNodeOptions, getNodeSubgraphOptions } from '@/client/@tanstack/react-query.gen'
import { getErrorMessage } from '@/lib/api-error'

// gid — в пути, а не в ?search: роутер разбирает search через JSON.parse, и 18 цифр потеряли бы точность.
// silent: ошибку (404, бэкенд недоступен) показывает сам экран, без глобального тоста.
const nodeQuery = (gid: string) => ({ ...getNodeOptions({ path: { gid } }), meta: { silent: true } })
const subgraphQuery = (gid: string, radius: number) => ({
  ...getNodeSubgraphOptions({ path: { gid }, query: { radius } }),
  meta: { silent: true },
})

export const Route = createFileRoute('/nodes/$gid')({
  validateSearch: z.object({ radius: z.number().int().min(1).max(3).default(1).catch(1) }),
  loaderDeps: ({ search }) => ({ radius: search.radius }),
  loader: ({ context: { queryClient }, params: { gid }, deps: { radius } }) =>
    Promise.all([
      queryClient.ensureQueryData(nodeQuery(gid)),
      queryClient.ensureQueryData(subgraphQuery(gid, radius)),
    ]),
  errorComponent: ({ error }) => <p className="text-destructive">{getErrorMessage(error)}</p>,
  component: NodePage,
})

// Заглушка до макета: проверяет, что карточка и окрестность доходят до экрана.
function NodePage() {
  const { gid } = Route.useParams()
  const { radius } = Route.useSearch()
  const { data: card } = useSuspenseQuery(nodeQuery(gid))
  const { data: subgraph } = useSuspenseQuery(subgraphQuery(gid, radius))

  return (
    <div className="space-y-2">
      <h1 className="font-mono text-lg">{card.node.gid}</h1>
      <p>
        {card.node.role} · приоритет {card.node.priority_score}
      </p>
      <p className="text-muted-foreground">{card.node.evidence}</p>
      <p className="text-sm text-muted-foreground">
        Окрестность, радиус {radius}: {subgraph.meta.n_nodes} узлов, {subgraph.meta.n_edges} рёбер · переводов:{' '}
        {card.transfers.length}
      </p>
    </div>
  )
}

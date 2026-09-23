import { createFileRoute } from '@tanstack/react-router'
import { AppHeader } from '@/components/app-header'
import { GidSearch } from '@/components/gid-search'
import { GraphPanel } from '@/components/graph/graph-panel'
import { NodeCard } from '@/components/node-card'
import { TopList } from '@/components/top-list'
import { graphQuery, metaQuery, nodeQuery, topQuery } from '@/lib/graph-data'

// gid — в пути, а не в ?search: роутер разбирает search через JSON.parse, и 18 цифр потеряли бы точность.
// Загрузчик не ждёт ответов: каркас экрана виден сразу, каждая колонка сама показывает загрузку, 404 и «сервер недоступен».
export const Route = createFileRoute('/nodes/$gid')({
  loader: ({ context: { queryClient }, params: { gid } }) => {
    void queryClient.prefetchQuery(metaQuery())
    void queryClient.prefetchQuery(topQuery())
    void queryClient.prefetchQuery(graphQuery())
    void queryClient.prefetchQuery(nodeQuery(gid))
  },
  component: NodePage,
})

function NodePage() {
  const { gid } = Route.useParams()
  return (
    <div className="flex h-svh min-h-[880px] min-w-[1440px] flex-col">
      <AppHeader />
      <div className="grid min-h-0 flex-1 grid-cols-[344px_minmax(0,1fr)_440px]">
        <aside className="flex min-h-0 flex-col border-r bg-background">
          <GidSearch />
          <TopList activeGid={gid} />
        </aside>
        <GraphPanel gid={gid} />
        <aside className="min-h-0 overflow-auto border-l bg-background">
          <NodeCard gid={gid} />
        </aside>
      </div>
    </div>
  )
}

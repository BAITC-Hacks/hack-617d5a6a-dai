import { createFileRoute, Link } from '@tanstack/react-router'
import { XIcon } from 'lucide-react'
import { NodeCard } from '@/components/node-card'
import { Button } from '@/components/ui/button'
import { nodeQuery } from '@/lib/graph-data'

// gid — в пути, а не в ?search: роутер разбирает search через JSON.parse, и 18 цифр потеряли бы точность.
export const Route = createFileRoute('/_workspace/nodes/$gid')({
  loader: ({ context: { queryClient }, params: { gid } }) => void queryClient.prefetchQuery(nodeQuery(gid)),
  component: NodeCardColumn,
})

function NodeCardColumn() {
  const { gid } = Route.useParams()
  return (
    <aside className="min-h-0 overflow-auto border-l bg-background">
      {/* Закрыть = снять выбор узла; видна при прокрутке, место под себя не занимает */}
      <div className="sticky top-0 z-10 flex h-0 justify-end">
        <Button
          variant="ghost"
          size="icon"
          className="mt-2.5 mr-2.5 bg-background/80 backdrop-blur-sm"
          aria-label="Закрыть карточку (Esc)"
          title="Закрыть карточку (Esc)"
          nativeButton={false}
          render={<Link to="/" />}
        >
          <XIcon />
        </Button>
      </div>
      <NodeCard gid={gid} />
    </aside>
  )
}

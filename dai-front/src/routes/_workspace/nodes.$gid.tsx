import { createFileRoute, Link } from '@tanstack/react-router'
import { ChevronLeftIcon, ChevronRightIcon, XIcon } from 'lucide-react'
import { useState } from 'react'
import { NodeCard } from '@/components/node-card'
import { Button } from '@/components/ui/button'
import { nodeQuery } from '@/lib/graph-data'
import { cn } from '@/lib/utils'

// gid — в пути, а не в ?search: роутер разбирает search через JSON.parse, и 18 цифр потеряли бы точность.
export const Route = createFileRoute('/_workspace/nodes/$gid')({
  loader: ({ context: { queryClient }, params: { gid } }) => void queryClient.prefetchQuery(nodeQuery(gid)),
  component: NodeCardColumn,
})

function NodeCardColumn() {
  const { gid } = Route.useParams()
  // Свёрнутая карточка — узкая полоса со стрелкой; ширину колонки задаёт сама (в сетке — auto).
  // Состояние живёт до закрытия карточки: смена узла его не сбрасывает.
  const [open, setOpen] = useState(true)
  return (
    <aside className={cn('min-h-0 overflow-auto border-l bg-background transition-[width] duration-200', open ? 'w-[360px] min-[1440px]:w-[440px]' : 'w-12')}>
      {/* Закрыть = снять выбор узла; видна при прокрутке, место под себя не занимает */}
      <div className={cn('sticky top-0 z-10 flex h-0 flex-col gap-1.5', open ? 'items-end pr-2.5' : 'items-center')}>
        {open && (
          <Button
            variant="ghost"
            size="icon"
            className="mt-2.5 bg-background/80 backdrop-blur-sm"
            aria-label="Закрыть карточку (Esc)"
            title="Закрыть карточку (Esc)"
            nativeButton={false}
            render={<Link to="/" />}
          >
            <XIcon />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          className={cn('bg-background/80 backdrop-blur-sm', !open && 'mt-2.5')}
          aria-expanded={open}
          aria-label={open ? 'Свернуть карточку' : 'Раскрыть карточку'}
          title={open ? 'Свернуть карточку' : 'Раскрыть карточку'}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <ChevronRightIcon /> : <ChevronLeftIcon />}
        </Button>
      </div>
      <div className={cn(!open && 'hidden')}>
        <NodeCard gid={gid} />
      </div>
    </aside>
  )
}

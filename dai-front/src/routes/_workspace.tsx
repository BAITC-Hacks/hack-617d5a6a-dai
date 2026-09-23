import { createFileRoute, Outlet, useNavigate, useParams } from '@tanstack/react-router'
import { useEffect } from 'react'
import { AppHeader } from '@/components/app-header'
import { GraphPanel } from '@/components/graph/graph-panel'
import { TopList } from '@/components/top-list'
import { graphQuery, metaQuery, topQuery } from '@/lib/graph-data'
import { cn } from '@/lib/utils'

// Рабочее место: шапка, очередь и схема сети живут в общем layout-маршруте и не пересоздаются,
// когда карточка узла (дочерний маршрут /nodes/$gid) открывается или закрывается — граф сохраняет раскладку и камеру.
// Загрузчик не ждёт ответов: каркас виден сразу, каждая колонка сама показывает загрузку и ошибки.
export const Route = createFileRoute('/_workspace')({
  loader: ({ context: { queryClient } }) => {
    void queryClient.prefetchQuery(metaQuery())
    void queryClient.prefetchQuery(topQuery())
    void queryClient.prefetchQuery(graphQuery())
  },
  component: Workspace,
})

function Workspace() {
  const gid = useParams({ strict: false }).gid ?? null
  const navigate = useNavigate()

  // Esc вне полей ввода закрывает карточку (снимает выбор узла)
  useEffect(() => {
    if (!gid) return
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      // открытое окно (справочник) закрывается своим Esc — карточку при этом не трогаем
      if (document.querySelector('[role="dialog"]')) return
      if (e.key === 'Escape' && !(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) void navigate({ to: '/' })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [gid, navigate])

  return (
    <div className="flex h-svh min-h-[880px] min-w-[1180px] flex-col">
      <AppHeader />
      <div className={cn('grid min-h-0 flex-1', gid
        ? 'grid-cols-[280px_minmax(0,1fr)_360px] min-[1440px]:grid-cols-[344px_minmax(0,1fr)_440px]'
        : 'grid-cols-[280px_minmax(0,1fr)] min-[1440px]:grid-cols-[344px_minmax(0,1fr)]')}>
        <aside className="flex min-h-0 flex-col border-r bg-background">
          <TopList activeGid={gid} />
        </aside>
        <GraphPanel gid={gid} />
        <Outlet />
      </div>
    </div>
  )
}

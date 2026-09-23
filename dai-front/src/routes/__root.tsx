import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, Outlet } from '@tanstack/react-router'
import { getErrorMessage } from '@/lib/api-error'

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: Outlet,
  errorComponent: ({ error }) => (
    <div className="grid h-svh place-items-center p-6 text-center">
      <div className="space-y-2">
        <p className="text-lg font-semibold">{getErrorMessage(error)}</p>
        <p className="text-muted-foreground">Проверьте, что бэкенд запущен на localhost:8000, и обновите страницу.</p>
      </div>
    </div>
  ),
})

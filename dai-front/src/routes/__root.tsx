import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, Link, Outlet } from '@tanstack/react-router'

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootLayout,
})

function RootLayout() {
  return (
    <div className="min-h-svh">
      <header className="flex items-center gap-4 border-b px-6 py-3">
        <Link to="/" className="font-heading font-semibold">
          App
        </Link>
      </header>
      <main className="mx-auto w-full max-w-5xl p-6">
        <Outlet />
      </main>
    </div>
  )
}

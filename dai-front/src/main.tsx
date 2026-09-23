import './index.css'
import './lib/api'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { ThemeProvider } from 'next-themes'
import { Toaster } from '@/components/ui/sonner'
import { queryClient } from '@/lib/query-client'
import { routeTree } from './routeTree.gen'

const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: 'intent',
  defaultPreloadStaleTime: 0, // TanStack Query owns caching
  scrollRestoration: true,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

async function enableMocks() {
  if (!import.meta.env.DEV || import.meta.env.VITE_MOCKS !== 'true') return
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledRequest: 'bypass' })
}

enableMocks().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
          <Toaster richColors />
        </QueryClientProvider>
      </ThemeProvider>
    </StrictMode>,
  )
})

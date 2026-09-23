import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { getErrorMessage } from '@/lib/api-error'

// Global error toasts. Opt out per query/mutation with `meta: { silent: true }`.
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (query.meta?.silent) return
      toast.error(getErrorMessage(error))
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _result, mutation) => {
      if (mutation.meta?.silent) return
      toast.error(getErrorMessage(error))
    },
  }),
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { BackendUnavailableError, getErrorMessage } from '@/lib/api-error'

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
    // Данные меняются только после перечитывания outputs/ бэкендом — повторно не запрашиваем.
    // ponytail: новые роли видны после перезагрузки страницы; сделать refetch по /meta, если понадобится вживую.
    // Повтор — только если бэкенд не ответил; 404/422 от повтора не изменятся.
    queries: { staleTime: Infinity, retry: (count, error) => count < 1 && error instanceof BackendUnavailableError },
  },
})

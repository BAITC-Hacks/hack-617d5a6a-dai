import { createFileRoute, redirect } from '@tanstack/react-router'
import { topQuery } from '@/lib/graph-data'

// Стартовый экран — первый узел топ-листа. Если бэкенд не ответил, ошибку покажет errorComponent корня.
export const Route = createFileRoute('/')({
  loader: async ({ context: { queryClient } }) => {
    const top = await queryClient.ensureQueryData(topQuery())
    throw redirect({ to: '/nodes/$gid', params: { gid: top.items[0].gid } })
  },
})

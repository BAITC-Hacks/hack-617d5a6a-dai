import { createFileRoute } from '@tanstack/react-router'

// Узел не выбран: только очередь и схема сети, карточки нет.
export const Route = createFileRoute('/_workspace/')({ component: () => null })

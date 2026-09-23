import { createFileRoute } from '@tanstack/react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export const Route = createFileRoute('/')({ component: HomePage })

function HomePage() {
  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>Стек готов</CardTitle>
        <CardDescription>React 19.3 · Vite 8 · Tailwind 4 · shadcn · TanStack · Hey API</CardDescription>
      </CardHeader>
      <CardContent>
        <Button onClick={() => toast.success('Работает')}>Проверить</Button>
      </CardContent>
    </Card>
  )
}

import { client } from '@/client/client.gen'
import { BackendUnavailableError } from '@/lib/api-error'
import { useAuth } from '@/stores/auth'

client.setConfig({ baseUrl: import.meta.env.VITE_API_URL })

client.interceptors.request.use((request) => {
  const token = useAuth.getState().token
  if (token) request.headers.set('Authorization', `Bearer ${token}`)
  return request
})

client.interceptors.response.use((response) => {
  if (response.status === 401) useAuth.getState().logout()
  return response
})

// Без ответа (сеть) или 502–504 (прокси не достучался) — иначе ошибка приходит пустой строкой без detail.
client.interceptors.error.use((error, response) =>
  !response || [502, 503, 504].includes(response.status) ? new BackendUnavailableError() : error,
)

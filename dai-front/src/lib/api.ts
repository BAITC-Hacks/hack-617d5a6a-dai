import { client } from '@/client/client.gen'
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

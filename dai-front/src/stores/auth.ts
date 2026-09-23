import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

type AuthState = {
  token: string | null
  setToken: (token: string | null) => void
  logout: () => void
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      setToken: (token) => set({ token }),
      logout: () => set({ token: null }),
    }),
    {
      name: 'auth',
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ token: s.token }),
    },
  ),
)

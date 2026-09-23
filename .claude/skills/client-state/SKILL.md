---
name: client-state
description: Where state lives in this app and how to write Zustand v5 stores (src/stores). Use this skill whenever adding or changing state that is shared between components — auth/session, cart, filters, wizard steps, UI toggles, persisted settings — or when deciding between Zustand, TanStack Query, URL search params and useState (стейт, стор, состояние, корзина, фильтры, persist), even if Zustand isn't mentioned.
---

# Client state (Zustand 5.0.15)

## Pick the right home first

| Kind of state | Where |
|---|---|
| Data from the backend (lists, details, anything fetched) | TanStack Query — see the `api-layer` skill. Never copy it into Zustand. |
| State that should survive reload/share via link (filters, tabs, page) | URL search params via TanStack Router `validateSearch` |
| Shared client state (auth token, cart, multi-step wizard, UI prefs) | Zustand store in `src/stores/` |
| State used by one component | `useState` |

Duplicating server data in a store is the most common bug source: two sources of truth that go out of sync.

## Store template

One store per domain, one file each: `src/stores/<domain>.ts`. Use the curried `create<T>()(...)` form — it's what makes TypeScript inference work with middleware.

```ts
import { create } from 'zustand'

type CartItem = { serviceId: number; qty: number }
type CartState = {
  items: CartItem[]
  add: (serviceId: number) => void
  remove: (serviceId: number) => void
  clear: () => void
}

export const useCart = create<CartState>()((set) => ({
  items: [],
  add: (serviceId) =>
    set((s) => {
      const found = s.items.find((i) => i.serviceId === serviceId)
      return {
        items: found
          ? s.items.map((i) => (i.serviceId === serviceId ? { ...i, qty: i.qty + 1 } : i))
          : [...s.items, { serviceId, qty: 1 }],
      }
    }),
  remove: (serviceId) => set((s) => ({ items: s.items.filter((i) => i.serviceId !== serviceId) })),
  clear: () => set({ items: [] }),
}))
```

Actions live inside the store; components never call `set` directly. Always update immutably.

## Reading in components

Select the smallest slice — a component re-renders only when its selected value changes.

```tsx
const count = useCart((s) => s.items.length)        // one value: plain selector

import { useShallow } from 'zustand/react/shallow'
const { add, remove } = useCart(useShallow((s) => ({ add: s.add, remove: s.remove }))) // several values
```

Returning a new object/array from a selector without `useShallow` causes an infinite re-render loop in v5. Never call `useCart()` with no selector.

## Outside React

```ts
useAuth.getState().token
useAuth.getState().logout()
```

That's how `src/lib/api.ts` reads the token for requests.

## Persisting

Only persist what must survive reload, and pick fields with `partialize`:

```ts
import { createJSONStorage, persist } from 'zustand/middleware'

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({ token: null, setToken: (token) => set({ token }), logout: () => set({ token: null }) }),
    { name: 'auth', storage: createJSONStorage(() => localStorage), partialize: (s) => ({ token: s.token }) },
  ),
)
```

Change the `name` key if the persisted shape changes incompatibly, otherwise old data from localStorage gets loaded into the new shape.

## Do not

- Create stores inside components or hooks (stores are module-level singletons in this SPA).
- Put functions, class instances or server responses into persisted state.
- Use React Context for global state — that's what the stores are for.

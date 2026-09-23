---
name: api-layer
description: How this project talks to the FastAPI backend — generated Hey API client in src/client, TanStack Query v5 hooks, auth token, FastAPI error shapes, MSW mocks, and regenerating after backend changes. Use this skill for ANY task that loads or sends data, adds a screen that shows backend data, handles loading/error states, login/logout, mocks, or mentions endpoints, API, backend, openapi, schema changes (запросы, бэкенд, эндпоинт, API, моки, загрузка данных, логин), even if the user doesn't name the libraries.
---

# API layer: FastAPI → Hey API → TanStack Query

```
Component
  → TanStack Query (cache, isPending, retries, invalidation)
    → Hey API SDK (typed fetch, generated into src/client from openapi.json)
      → FastAPI (dev: Vite proxy /api → :8000)
```

Everything in `src/client/` is generated from `openapi.json`. The types there are the contract with the backend, so hand-written fetch calls or hand-written types would silently drift from it.

## Rules

- Never write `fetch`/`axios` calls or response types by hand. Use the generated functions.
- Never edit `src/client/**` or any `*.gen.ts` — they are overwritten by `npm run gen`.
- Don't set `baseUrl` or auth headers in components; that lives in `src/lib/api.ts`.
- If an endpoint you need is missing from `src/client`, the schema is stale or the backend doesn't have it yet. Say so; don't invent it.

## After the backend changes

```bash
curl -o openapi.json http://<backend-host>:8000/openapi.json   # refresh snapshot
npm run gen                                                    # regenerate src/client
npm run typecheck                                              # shows every place the contract broke
```

Fix the type errors rather than casting them away — each one is a real mismatch with the backend.

## Naming map (FastAPI → generated)

FastAPI uses `generate_unique_id_function=lambda r: r.name`, so the Python function name becomes the operation name:

| FastAPI endpoint function | Query | Mutation | Key | Mock |
|---|---|---|---|---|
| `def list_services(...)` (GET) | `listServicesOptions` | — | `listServicesQueryKey` | `handleListServices` |
| `def create_order(...)` (POST) | — | `createOrderMutation` | — | `handleCreateOrder` |

Imports: queries/mutations/keys from `@/client/@tanstack/react-query.gen`, plain SDK functions from `@/client/sdk.gen`, types from `@/client/types.gen`, zod schemas from `@/client/zod.gen`, mocks from `@/client/msw.gen`.

Request options mirror FastAPI parameters and keep snake_case: `path` (path params), `query` (query params), `body` (JSON body).

## Reading data

```tsx
import { useQuery } from '@tanstack/react-query'
import { getServiceOptions, listServicesOptions } from '@/client/@tanstack/react-query.gen'

const services = useQuery(listServicesOptions({ query: { limit: 20 } }))
// extra TanStack options: spread, then add
const service = useQuery({
  ...getServiceOptions({ path: { service_id: id } }),
  enabled: id > 0,
})

if (services.isPending) return <Skeleton className="h-24" />
if (services.isError) return null // global toast already shows the error
services.data // fully typed
```

TanStack Query v5 names: `isPending` (not `isLoading` for first load), `gcTime` (not `cacheTime`), single object argument everywhere.

## Writing data

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createOrderMutation, listServicesQueryKey } from '@/client/@tanstack/react-query.gen'

const qc = useQueryClient()
const createOrder = useMutation({
  ...createOrderMutation(),
  onSuccess: () => qc.invalidateQueries({ queryKey: listServicesQueryKey() }),
})
createOrder.mutate({ body: { service_id: 1, address: 'Астана' } })
```

`listServicesQueryKey()` without params matches every cached `listServices` query (any `query`/`path`), because TanStack matches keys partially. Pass params only to invalidate one variant.

## Outside components

Plain SDK functions return `{ data, error }` and don't throw:

```ts
import { listServices } from '@/client/sdk.gen'
const { data, error } = await listServices({ query: { limit: 5 } })
```

In TanStack Router loaders use the query client from router context so the cache is shared:
`loader: ({ context }) => context.queryClient.ensureQueryData(listServicesOptions())`.

## Auth

- Token lives in the Zustand store `useAuth` (`src/stores/auth.ts`, persisted to localStorage).
- `src/lib/api.ts` adds `Authorization: Bearer <token>` to every request and logs out on 401.
- FastAPI's `OAuth2PasswordRequestForm` login is form-urlencoded; the generated client already sends it that way:

```tsx
const login = useMutation({
  ...loginMutation(),
  onSuccess: (data) => useAuth.getState().setToken(data.access_token),
})
login.mutate({ body: { username, password } })
```

## Errors

Generated query/mutation helpers throw the parsed FastAPI error body. Shapes:
- `HTTPException` → `{ "detail": "text" }`
- validation (422) → `{ "detail": [{ "loc": ["body", "address"], "msg": "...", "type": "..." }] }`
- network failure → a regular `Error`

Use the helpers in `src/lib/api-error.ts`: `getErrorMessage(error)` for any error, `getFieldErrors(error)` to map 422 to form fields.

Global toasts are wired in `src/lib/query-client.ts` (QueryCache/MutationCache `onError`). Don't add another toast per call. To handle an error locally instead, set `meta: { silent: true }` on that query/mutation.

## Mocks (backend not ready yet)

`.env.development` has `VITE_MOCKS=true`; MSW starts in dev only and never ships to production. Add handlers in `src/mocks/browser.ts` using generated, typed handlers:

```ts
import { handleGetService, handleListServices } from '@/client/msw.gen'

export const worker = setupWorker(
  handleListServices({ body: [{ id: 1, title: 'Demo', price: 1000, description: null }] }),
  handleGetService(({ params }) => Response.json({ id: Number(params.service_id), title: 'Demo', price: 1000, description: null })),
)
```

Never write `http.get(...)` by hand — generated handlers break at compile time when the schema changes, hand-written ones silently lie. Unmocked requests pass through to the real backend (`onUnhandledRequest: 'bypass'`), so delete a handler as soon as its endpoint works.

## Do not

- Upgrade `typescript` to 7.x — Hey API's generator needs the TS 6 JS API.
- Run `npm audit fix --force` — it downgrades Hey API. Security fixes go through `overrides` in package.json.

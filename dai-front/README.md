# dai-front

Фронтенд DAI: SPA на React 19.3 + Vite 8 + Tailwind 4 + shadcn/ui + TanStack Router/Query + Zustand + Hey API. Бэкенд — FastAPI, контракт — [`openapi.json`](openapi.json).

Правила для агентов: [`CLAUDE.md`](CLAUDE.md). Скилы — в [`../.claude/skills`](../.claude/skills).

## Быстрый старт

Нужен Node ≥ 22.18 (проверено на 24.x, см. `.nvmrc`).

```bash
cd dai-front
npm ci                                # ровно версии из package-lock.json, не npm install
cp .env.example .env.development      # локальные переменные, включает моки
npm run dev                           # http://localhost:5173
```

С моками (`VITE_MOCKS=true`) фронт работает без бэкенда: запросы перехватывает MSW.

## Команды

| Команда | Что делает |
|---|---|
| `npm run dev` | dev-сервер |
| `npm run dev:host` | то же, доступно с телефона по IP |
| `npm run gen` | перегенерировать `src/client` из `openapi.json` |
| `npm run typecheck` | `tsc -b` |
| `npm run lint` | oxlint |
| `npm run build` | typecheck + сборка в `dist/` |
| `npm run preview` | посмотреть собранный `dist/` |

## Переменные окружения

В git лежит только [`.env.example`](.env.example), остальные `.env*` игнорируются.

| Переменная | Dev | Prod |
|---|---|---|
| `VITE_API_URL` | `/api` (через Vite-прокси) | полный URL бэкенда, `https://...` |
| `VITE_MOCKS` | `true` — моки MSW | не задавать, в прод моки не попадают |
| `API_PROXY_TARGET` | куда проксировать `/api`, по умолчанию `http://localhost:8000` | — |

`VITE_*` попадают в бандл — секреты туда не класть.

## Подключение бэкенда

Когда бэкенд поднят:

```bash
curl -o openapi.json http://<IP-бэкенда>:8000/openapi.json
npm run gen
npm run typecheck                     # покажет, что сломалось после смены схемы
API_PROXY_TARGET=http://<IP-бэкенда>:8000 npm run dev
```

Для работы с живым бэкендом поставь `VITE_MOCKS=false` в `.env.development`.

## Деплой

- Root directory: `dai-front`
- Install: `npm ci`, build: `npm run build`, output: `dist`
- Node: 24
- Env: `VITE_API_URL=https://<бэкенд>` в настройках хостинга
- SPA: все пути должны отдавать `index.html` (rewrite `/* → /index.html`), иначе прямые ссылки на страницы дадут 404
- Бэкенд должен разрешить CORS для домена фронта: в проде запросы идут напрямую, без прокси

## Структура

```
openapi.json              контракт с FastAPI
src/client/               сгенерировано Hey API — не редактировать
src/routeTree.gen.ts      сгенерировано роутером — не редактировать
src/routes/               файловые маршруты TanStack Router
src/components/ui/        компоненты shadcn
src/components/           свои компоненты
src/stores/               Zustand-сторы
src/lib/                  api-клиент, ошибки API, QueryClient
src/mocks/                MSW (только dev)
```

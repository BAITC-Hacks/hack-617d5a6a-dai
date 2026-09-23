# dai-front — интерфейс «Граф денег»

Экран просмотра для AML-аналитика: схема сети с направлением переводов, роли и кластеры узлов, поиск по `gid`, топ-лист приоритетов с обоснованием (ТЗ, must have 5). Контекст кейса и запуск всего решения — в [корневом README](../README.md).

## Состояние

Каркас: стек настроен, проект собирается и запускается, данные — моки. Экраны кейса ещё не реализованы.

| Экран | Что показывает | Статус |
|---|---|---|
| Поиск по `gid` | переход к узлу по идентификатору | план |
| Схема сети | направленные переводы, подсветка ролей и кластеров | план |
| Карточка узла | роль, `role_score`, кластер, `priority_score`, `evidence`, входящие и исходящие связи | план |
| Топ-лист | ≥ 20 узлов по `priority_score` с обоснованием | план |

## Запуск

Нужен Node ≥ 22.18 (проверено на 24.x, см. `.nvmrc`).

```bash
cd dai-front
npm ci                                # ровно версии из package-lock.json
cp .env.example .env.development      # локальные переменные, включает моки
npm run dev                           # http://localhost:5173
```

С моками (`VITE_MOCKS=true`) интерфейс работает без бэкенда: запросы перехватывает MSW.

## Данные

- Источник: пока моки MSW (`src/mocks/`) по примерной схеме `openapi.json`. Контракт с пайплайном (роли, кластеры, связи) появится вместе с ним — см. [гипотезу по передаче данных](../docs/hypothesis_ivan_din.md#3-передача-между-иваном-и-дином).
- `gid` в браузере — всегда строка: часть значений больше `Number.MAX_SAFE_INTEGER`. Поиск сравнивает строки.

## Стек

React 19.3 · TypeScript 6 · Vite 8 · Tailwind CSS 4 · shadcn/ui (Base UI) · TanStack Router + Query · Zustand · Hey API (типизированный клиент из OpenAPI) · MSW (моки) · react-hook-form + zod · oxlint.

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

```bash
curl -o openapi.json http://<IP-бэкенда>:8000/openapi.json
npm run gen
npm run typecheck                     # покажет, что сломалось после смены схемы
API_PROXY_TARGET=http://<IP-бэкенда>:8000 npm run dev
```

Для работы с живым бэкендом поставь `VITE_MOCKS=false` в `.env.development`.

## Деплой

- Root directory: `dai-front`; install `npm ci`, build `npm run build`, output `dist`, Node 24
- Env в настройках хостинга: `VITE_API_URL=https://<бэкенд>`
- SPA: все пути отдают `index.html` (rewrite `/* → /index.html`), иначе прямые ссылки дадут 404
- Бэкенд должен разрешить CORS для домена фронта: в проде запросы идут напрямую, без прокси

## Структура

```
openapi.json              контракт с бэкендом
src/client/               сгенерировано Hey API — не редактировать
src/routeTree.gen.ts      сгенерировано роутером — не редактировать
src/routes/               файловые маршруты TanStack Router
src/components/ui/        компоненты shadcn
src/components/           свои компоненты
src/stores/               Zustand-сторы
src/lib/                  api-клиент, ошибки API, QueryClient
src/mocks/                MSW (только dev)
```

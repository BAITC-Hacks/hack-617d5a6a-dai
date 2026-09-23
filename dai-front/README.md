# dai-front — интерфейс «Граф денег»

Экран просмотра для AML-аналитика: схема сети с направлением переводов, роли и кластеры узлов, поиск по `gid`, топ-лист приоритетов с обоснованием (ТЗ, must have 5). Контекст кейса и запуск всего решения — в [корневом README](../README.md).

## Состояние

Каркас: стек настроен, проект собирается и запускается, клиент API сгенерирован из контракта бэкенда. Экраны кейса ещё не реализованы.

| Экран | Что показывает | Статус |
|---|---|---|
| Поиск по `gid` | переход к узлу по идентификатору | план |
| Схема сети | направленные переводы, подсветка ролей и кластеров | план |
| Карточка узла | роль, `role_score`, кластер, `priority_score`, `evidence`, входящие и исходящие связи | план |
| Топ-лист | ≥ 20 узлов по `priority_score` с обоснованием | план |

## Запуск

Нужны Node ≥ 22.18 (проверено на 24.x, см. `.nvmrc`) и Python 3.11–3.13 для бэкенда.

Бэкенд (терминал 1, из корня репозитория; подробнее в [backend/README.md](../backend/README.md)):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Фронт (терминал 2):

```bash
cd dai-front
npm ci                                # ровно версии из package-lock.json
cp .env.example .env.development      # локальные переменные
npm run dev                           # http://localhost:5173
```

Запросы `/api/*` Vite проксирует на `localhost:8000`. MSW включён (`VITE_MOCKS=true`), но своих обработчиков пока нет, поэтому все запросы уходят на бэкенд. Без запущенного бэкенда запросы падают сетевой ошибкой.

## Данные

- Источник: API из [`backend/`](../backend/README.md) (порт 8000, в dev через прокси `/api`). Контракт `openapi.json` генерируется из бэкенда. Бэкенд сам обновляет `openapi.json` и `src/client/` в одном коммите со своими изменениями, поэтому после `git pull` запускать `npm run gen` не нужно.
- Эндпоинты: `/meta`, `/graph`, `/search`, `/nodes/{gid}`, `/nodes/{gid}/subgraph`, `/top`, `/clusters`, `/clusters/{cluster_id}`, `/health`. Хуки — из `@/client/@tanstack/react-query.gen` (`getNodeOptions`, `searchNodesOptions`, `getTopNodesOptions` и т. д.).
- До готовности пайплайна бэкенд отдаёт заглушку на реальных `gid` (`meta.mock: true`, в `evidence` префикс `mock`). Роли и скоры в ней — простые пороги, не результат анализа.
- Чтобы работать без бэкенда, регистрируй моки в `src/mocks/browser.ts` через сгенерированные `handle*` из `@/client/msw.gen`.
- Смысл полей и статусы хронологии — в [гипотезе по передаче данных](../docs/hypothesis_ivan_din.md).
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

## Бэкенд на другой машине

```bash
API_PROXY_TARGET=http://<IP-бэкенда>:8000 npm run dev
```

Если схема на той машине новее закоммиченной:

```bash
curl -o openapi.json http://<IP-бэкенда>:8000/openapi.json
npm run gen
npm run typecheck                     # покажет, что сломалось после смены схемы
```

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

# dai-front — интерфейс «Граф денег»

Экран просмотра для AML-аналитика: схема сети с направлением переводов, роли и кластеры узлов, поиск по `gid`, топ-лист приоритетов с обоснованием (ТЗ, must have 5). Контекст кейса и запуск всего решения — в [корневом README](../README.md). Решения по экранам, схеме сети и визуальному языку — в [DESIGN.md](DESIGN.md).

## Состояние

Каркас: стек настроен, проект собирается и запускается, клиент API сгенерирован из контракта бэкенда. Экраны кейса ещё не реализованы: маршрут `/nodes/$gid` уже грузит карточку и окрестность узла, но выводит их временной заглушкой до макета.

| Экран | Что показывает | Статус |
|---|---|---|
| Поиск по `gid` | переход к узлу по идентификатору | план |
| Схема сети | направленные переводы, подсветка ролей и кластеров | план |
| Карточка узла | роль, `role_score`, кластер, `priority_score`, `evidence`, входящие и исходящие связи | план |
| Топ-лист | ≥ 20 узлов по `priority_score` с обоснованием | план |

## Запуск

Нужен Node ≥ 22.18 (проверено на 24.x, см. `.nvmrc`) и запущенный бэкенд на `localhost:8000` ([как запустить](../backend/README.md)).

```bash
cd dai-front
npm ci                                # ровно версии из package-lock.json
cp .env.example .env.development      # локальные переменные
npm run dev                           # http://localhost:5173
```

Запросы `/api/*` Vite проксирует на `localhost:8000`. MSW включён (`VITE_MOCKS=true`), но своих обработчиков пока нет, поэтому все запросы уходят на бэкенд. Если бэкенд не отвечает, экран показывает «Сервер анализа недоступен» отдельно от «не найдено».

## Данные

- Источник: API из [`backend/`](../backend/README.md) (порт 8000, в dev через прокси `/api`). Контракт `openapi.json` генерируется из бэкенда. Бэкенд сам обновляет `openapi.json` и `src/client/` в одном коммите со своими изменениями, поэтому после `git pull` запускать `npm run gen` не нужно.
- Очередь проверки (левая колонка) — узлы с `in_queue: true` из `/graph` по убыванию `priority_score` (`useQueue()` в `src/lib/graph-data.ts`); правило очереди — `queue_rule` из `/meta`. `/top` отдаёт только 50 строк, поэтому очередь из него не строится.
- Карточка узла (`src/components/node-card.tsx` + `node-card/`): кроме `evidence` показывает `role_checks` чек-листом, `score_terms` / `n_terms_above_p95` / `priority_raw` («почему такой приоритет»), `n_seed_upstream`, `next_request`, `limitations`, бейджи `in_queue` и `fast_transit_flag`. Вкладка «Пары» — `pairs` из `/nodes/{gid}` (вход → выход по дате входа, первые 50 + «Показать все»).
- Эндпоинты: `/meta`, `/graph`, `/search`, `/nodes/{gid}`, `/nodes/{gid}/subgraph`, `/top`, `/clusters`, `/clusters/{cluster_id}`, `/health`. Хуки — из `@/client/@tanstack/react-query.gen` (`getNodeOptions`, `searchNodesOptions`, `getTopNodesOptions` и т. д.).
- До готовности пайплайна бэкенд отдаёт заглушку на реальных `gid` (`meta.mock: true`, в `evidence` префикс `mock`). Роли и скоры в ней — простые пороги, не результат анализа.
- Чтобы работать без бэкенда, регистрируй моки в `src/mocks/browser.ts` через сгенерированные `handle*` из `@/client/msw.gen`.
- Смысл полей и статусы хронологии — в [гипотезе по передаче данных](../docs/hypothesis_ivan_din.md).
- `gid` в браузере — всегда строка: часть значений больше `Number.MAX_SAFE_INTEGER`. Поиск сравнивает строки. В URL `gid` идёт в путь (`/nodes/$gid`), а не в `?search`: роутер разбирает search через `JSON.parse`, и 18 цифр потеряли бы точность.
- Где что хранится: серверные данные — в TanStack Query (`staleTime: Infinity`, данные меняются только при перечитывании `outputs/` бэкендом); выбранный узел и `radius` — в URL; hover и скрытые роли легенды — в `src/stores/graph-view.ts`.
- Ошибки: 404/422 не повторяются, показывается `detail` бэкенда; сеть или 502–504 → `BackendUnavailableError` (`src/lib/api-error.ts`), один повтор.

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
src/routes/nodes.$gid.tsx узел: карточка + окрестность, ?radius=1..3
src/components/ui/        компоненты shadcn
src/components/           свои компоненты
src/stores/graph-view.ts  hover и скрытые роли — общее для графа, топ-листа и карточки
src/lib/                  api-клиент, ошибки API, QueryClient
src/lib/format.ts         суммы «3 848 436 ₸» / «3,8 млн ₸», даты «12.07»
src/mocks/                MSW (только dev)
```

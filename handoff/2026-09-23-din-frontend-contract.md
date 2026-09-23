# Дину: контракт API и данные для экранов

Дата: 23.09.2026, после коммита `5e6dcd7` в `main`; запуск бэкенда из корня — с 15:40. План на остаток дня: `docs/execution_plan_2026-09-23.md`. Папка `handoff/` удаляется к сдаче.

## Что уже в репозитории

- `backend/` — FastAPI-сервис; из него генерируется `dai-front/openapi.json`. Пока `outputs/` пуст, сервис отдаёт заглушку на реальных `gid` из `task/data`: роли по простым порогам, кластер = слабосвязная компонента (35 штук), топ-20. В ответах `meta.mock: true`, в `evidence` префикс `mock`.
- `dai-front/openapi.json` и `src/client/` перегенерированы и закоммичены; typecheck и lint проходят. `npm run gen` не нужен.
- Правила контракта: поля только добавляются, существующие не переименовываются и не удаляются. После моего изменения бэкенда я сам перегенерирую клиент и коммичу `openapi.json` + `src/client/` одним коммитом.

## Запуск

```bash
git pull --rebase --autostash
```

Бэкенд (терминал 1):

```bash
python3 -m venv .venv && . .venv/bin/activate      # из корня репозитория, Python 3.11–3.13
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Фронт (терминал 2):

```bash
cd dai-front
npm ci
cp .env.example .env.development     # если ещё нет
npm run dev
```

С `VITE_MOCKS=true` и без зарегистрированных `handle*` в `src/mocks/browser.ts` запросы уходят через прокси `/api` на бэкенд (`onUnhandledRequest: 'bypass'`). Переключать ничего не нужно. Если хочешь работать без бэкенда — мокай через сгенерированные `handleGetGraph`, `handleGetNode` и т. д. из `@/client/msw.gen`.

Проверка, что бэкенд жив:

```bash
curl localhost:8000/health
curl "localhost:8000/search?q=1000000003&limit=3"
```

Документация с примерами ответов: http://localhost:8000/docs

## Эндпоинты и хуки

| Путь | Хук из `@/client/@tanstack/react-query.gen` | Для чего на экране |
|---|---|---|
| `GET /meta` | `getMetaOptions` | сводка (2 248 узлов, 3 119 рёбер, период), источник `outputs`/`mock`, словарь ролей для легенды |
| `GET /graph?cluster_id&role&min_priority&limit` | `getGraphOptions` | схема сети целиком (около 1 МБ JSON, 0,2 с) или срез; рёбра только между возвращёнными узлами; `meta.truncated` — обрезано ли по `limit` |
| `GET /search?q&limit` | `searchNodesOptions` | поиск по началу `gid`; точное совпадение первым; `total` — сколько всего совпало |
| `GET /nodes/{gid}` | `getNodeOptions` | карточка: узел, `in_edges`, `out_edges`, `transfers` (отдельные переводы с датами, по дате) |
| `GET /nodes/{gid}/subgraph?radius=1..3` | `getNodeSubgraphOptions` | окрестность узла для демо «назовите gid» (radius=1 у топового узла: 86 узлов, 88 рёбер) |
| `GET /top?limit=20` | `getTopNodesOptions` | топ-лист: `rank`, `gid`, `role`, `priority_score`, `why` |
| `GET /clusters` | `listClustersOptions` | паспорта: `n_nodes`, `n_seed`, `sum_kzt_internal`, `top_gids`, `hypothesis` |
| `GET /clusters/{cluster_id}` | `getClusterOptions` | паспорт плюс подграф кластера |
| `POST /reload` | `reloadDataMutation` | перечитать `outputs/` после прогона пайплайна (кнопка не нужна, это для меня) |

Типы — `@/client/types.gen`: `NodeOut`, `EdgeOut`, `TransferOut`, `GraphResponse`, `NodeCard`, `SearchResponse`, `TopNode`, `ClusterOut`, `MetaResponse`, `Role`.

## Поля узла (`NodeOut`) и как их показывать

| Поле | Смысл | На экране |
|---|---|---|
| `gid` | идентификатор, **строка** | подпись, поиск — сравнивать строки |
| `role` | одна из `consolidator` · `transit` · `distributor` · `terminal` · `coordinator` · `peripheral` | цвет узла плюс подпись словом (цвет не заменяет текст) |
| `role_score` | сила поддержки правила, 0–1 | в карточке; это не вероятность |
| `cluster_id` | номер кластера | форма или обводка узла, фильтр в `/graph` |
| `priority_score` | приоритет проверки, 0–1 | размер узла, сортировка топ-листа |
| `evidence` | почему такая роль, числа, до 200 символов | текст в карточке как есть |
| `depth` | колено обхода, 0 = seed | `depth=4` пометить как «граница выгрузки» |
| `is_seed` | один из 81 исходных | отдельный маркер |
| `in_deg`/`out_deg`, `in_kzt`/`out_kzt`, `in_tx`/`out_tx` | контрагенты, суммы, число переводов внутри графа | карточка |
| `truncated_by_depth` | узел на 4-м колене без исходящих | подпись «исходящие не выгружены», не «деньги остались» |

Рёбра (`EdgeOut`): `src → dst` — направление перевода, стрелка обязательна; `sum_kzt`, `n_tx` — толщина или подпись; `depth` — колено.

Переводы (`TransferOut`): `date` — строка `YYYY-MM-DD`, точность до дня; порядок внутри дня неизвестен, так и подписывать.

## Ошибки

- Неизвестный `gid` или кластер → 404, тело `{"detail": "gid … не найден"}`; `getErrorMessage` из `src/lib/api-error.ts` его покажет.
- Неверные параметры → 422 стандартной формы FastAPI.
- Пока бэкенд не запущен, запросы через прокси падают сетевой ошибкой — состояние «бэкенд недоступен» стоит показать отдельно от «ничего не найдено».

## Сценарий демо, под который строить экран

1. Жюри называет `gid` → поле поиска → `/search?q=` → переход к узлу.
2. Экран показывает окрестность `/nodes/{gid}/subgraph?radius=1` со стрелками, цветами ролей и кластером.
3. Карточка `/nodes/{gid}`: роль с `evidence`, входящие и исходящие, переводы по датам.
4. Топ-20 рядом или отдельной вкладкой; клик по строке — тот же переход.

## Что изменится дальше (только добавление полей)

- В `TransferOut` для карточки: статус хронологии пары переводов («вход раньше выхода» / «один день, порядок неизвестен» / «выход раньше входа»), допустимый вывод и следующий запрос — по `docs/hypothesis_ivan_din.md`.
- Один агрегированный риск-скор с объяснимым порогом (Амир прорабатывает); появится как новое поле рядом с `priority_score`, старое поле останется.
- Когда пайплайн запишет `outputs/`, `meta.mock` станет `false`, роли и кластеры изменятся, контракт — нет.

Вопросы по полям и ошибкам — мне; библиотека графа на твой выбор (в исследовании упоминали Cytoscape.js: стрелки, стили, поиск, layouts).

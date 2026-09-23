# backend — API «Граф денег»

FastAPI-сервис, который отдаёт интерфейсу роли, кластеры, приоритеты и связи узлов. Контракт с фронтом — [`dai-front/openapi.json`](../dai-front/openapi.json); он генерируется из этого кода, руками не правится.

## Запуск

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Проверка: `curl localhost:8000/health` → `{"status":"ok","mock":true}`; схема — `localhost:8000/openapi.json`, документация — `localhost:8000/docs`.

## Источник данных

| Условие | `source` | Что отдаётся |
|---|---|---|
| В `outputs/` есть `nodes_roles.csv`, `clusters.csv`, `top_nodes.csv` | `outputs` | результат пайплайна |
| Файлов нет | `mock` | заглушка: роли по простым порогам на признаках стартового кода, кластер = слабосвязная компонента, реальные `gid` из `task/data` |

Заглушка нужна, чтобы интерфейс работал на настоящих идентификаторах до готовности пайплайна. Её роли и скоры — не результат анализа; в ответах стоит `mock: true`, в `evidence` — префикс `mock`. После прогона пайплайна: `curl -X POST localhost:8000/reload`.

Переменные окружения: `DAI_DATA_DIR` (по умолчанию `../task/data`), `DAI_OUTPUTS_DIR` (по умолчанию `../outputs`).

## Эндпоинты

| Метод и путь | Что возвращает |
|---|---|
| `GET /health` | статус и флаг `mock` |
| `GET /meta` | сводка по выгрузке, источник, словарь ролей для легенды |
| `GET /graph?cluster_id=&role=&min_priority=&limit=` | узлы и рёбра между ними (весь граф или срез) |
| `GET /search?q=&limit=` | узлы по началу `gid`, точное совпадение первым |
| `GET /nodes/{gid}` | карточка: узел, входящие и исходящие рёбра, отдельные переводы с датами |
| `GET /nodes/{gid}/subgraph?radius=` | окрестность узла для экрана (1–3 шага) |
| `GET /top?limit=` | ранжированный список приоритетов (`top_nodes.csv`) |
| `GET /clusters`, `GET /clusters/{cluster_id}` | паспорта кластеров; по одному — ещё и подграф |
| `POST /reload` | перечитать `outputs/` без перезапуска |

`gid` везде строка: значения `int64` больше `Number.MAX_SAFE_INTEGER`. Неизвестный `gid` или кластер → 404 с `detail`.

## Как менять контракт

Поля только добавляются. После правки схем или маршрутов:

```bash
cd backend && python export_openapi.py
cd ../dai-front && npm run gen && npm run typecheck
```

Оба результата (`openapi.json` и `src/client/`) коммитятся вместе с изменением бэкенда.

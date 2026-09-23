# Проект

Фронтенд для хакатона: SPA без SSR. Бэкенд — FastAPI (делает другой человек), контракт — `openapi.json`.

## Стек (версии закреплены, не обновлять без необходимости)

React 19.3 · TypeScript 6.0.3 · Vite 8.3 · Tailwind CSS 4.3 · shadcn/ui 4.21 (Base UI, стиль nova) · TanStack Router 1.170 · TanStack Query 5.103 · Zustand 5.0 · Hey API 0.99 (генерация клиента) · MSW 2.15 · react-hook-form 7.88 + zod 4.6. Node ≥ 22.18 (проверено на 24.13.1).

## Скилы — читай перед работой в своей области

| Задача | Скил |
|---|---|
| Любые запросы к бэкенду, загрузка данных, логин, моки, обновление схемы | `api-layer` |
| Общее состояние (корзина, сессия, фильтры) | `client-state` |
| Формы и валидация | `forms` |
| Стили, цвета, тема, классы Tailwind | `tailwind-v4` |
| UI-компоненты shadcn (официальный) | `shadcn` |
| Роутинг, параметры, загрузчики, guards (официальный, TanStack) | `router-core` → нужный подскил |
| Настройка плагина роутера (официальный, TanStack) | `router-plugin` |

## Команды

```bash
npm run dev          # dev-сервер, моки включены (.env.development)
npm run dev:host     # то же, доступно с телефона по IP
npm run gen          # перегенерировать src/client из openapi.json
npm run typecheck    # tsc -b
npm run lint         # oxlint
npm run build        # typecheck + сборка
```

Обновить схему бэкенда: `curl -o openapi.json http://<IP>:8000/openapi.json && npm run gen && npm run typecheck`.
Прокси на чужой бэкенд в dev: `API_PROXY_TARGET=http://<IP>:8000 npm run dev`.

## Структура

```
openapi.json              контракт с FastAPI (коммитится)
src/client/               СГЕНЕРИРОВАНО Hey API — не редактировать
src/routeTree.gen.ts      СГЕНЕРИРОВАНО роутером — не редактировать, коммитится
src/routes/               файловые маршруты TanStack Router
src/components/ui/        компоненты shadcn (можно править)
src/components/           свои компоненты
src/stores/               Zustand-сторы (по одному на домен)
src/lib/api.ts            baseUrl, токен, 401 → logout
src/lib/api-error.ts      getErrorMessage / getFieldErrors для ошибок FastAPI
src/lib/query-client.ts   QueryClient + глобальные тосты ошибок
src/mocks/browser.ts      MSW-моки (только dev)
```

## Правила

- Запросы — только через сгенерированные функции из `@/client/...`. Никаких ручных `fetch`/axios и ручных типов ответа.
- Файлы `*.gen.ts` и `src/client/**` не редактировать — их перезаписывает генерация.
- Серверные данные живут в TanStack Query, не копировать их в Zustand.
- Цвета — только токены темы (`bg-primary`, `text-muted-foreground`, …), без `bg-blue-500` для элементов темы.
- Tailwind v4: конфиг только в `src/index.css` (`@theme`). `tailwind.config.js` не создавать.
- Новые UI-компоненты: `npx shadcn@4.21.0 add <name>` (версия закреплена, скил shadcn пишет `@latest` — в этом проекте используй 4.21.0).
- Моки — только через сгенерированные `handle*` из `@/client/msw.gen`, руками `http.get()` не писать.
- Секреты не класть в переменные `VITE_*` — они попадают в бандл.

## Запрещено

- Обновлять `typescript` до 7.x (ломает генератор Hey API).
- `npm audit fix --force` (откатывает Hey API). Исправления уязвимостей — через `overrides` в package.json.
- Менять `.npmrc` (`save-exact`, `ignore-scripts` — защита от supply chain атак).
- Ставить сторонние скилы/плагины без согласования.

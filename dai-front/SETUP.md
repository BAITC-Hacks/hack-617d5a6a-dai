# SETUP — инструкция для Claude Code

Этот каталог — готовый каркас фронтенда. Все версии уже подобраны и проверены вместе (Node 24.13.1: `npm ci`, генерация клиента, typecheck, build, lint, `npm audit` = 0 уязвимостей). Твоя задача — развернуть его, проверить и отчитаться. Ничего не обновляй и не добавляй сверх описанного.

## 0. Предусловия

- `node -v` должен быть ≥ 22.18 (рекомендуется 24.x). Если меньше — остановись и сообщи.
- Работай в корне проекта (там, где лежат `package.json` и этот файл).

## 1. Установка зависимостей

```bash
npm ci
```

- Ставит ровно версии из `package-lock.json`. Не используй `npm install` вместо `npm ci`.
- `.npmrc` содержит `ignore-scripts=true` и `save-exact=true` — не меняй. Единственный пакет с install-скриптом (msw) он не нужен: `public/mockServiceWorker.js` уже лежит в проекте.

## 2. Проверки (все должны пройти)

```bash
npm run gen         # генерация src/client из openapi.json — ожидается "✓ ./src/client"
npm run build       # tsc -b + vite build — без ошибок
npm run lint        # oxlint — 0 errors
npm audit           # ожидается: found 0 vulnerabilities
```

Если `npm audit` покажет новые уязвимости: НЕ запускай `npm audit fix --force`. Выведи отчёт (пакет, severity, путь зависимости) и остановись — исправления делаются через `overrides` в package.json после согласования.

## 3. Смоук-тест

```bash
npm run dev
```

Открой http://localhost:5173 — должна быть карточка «Стек готов», кнопка «Проверить» показывает тост. В консоли браузера должно появиться сообщение MSW о включении моков (моки включены в `.env.development`). Останови сервер.

## 4. Скилы

Уже лежат в `.claude/skills/` — ничего устанавливать не нужно. Проверь, что на месте:

| Скил | Источник |
|---|---|
| `shadcn` | официальный, github.com/shadcn-ui/ui (хэш в `skills-lock.json`) |
| `router-core` (+ подскилы), `router-plugin` | официальные, поставляются внутри npm-пакетов `@tanstack/router-core` / `@tanstack/router-plugin` той же версии |
| `api-layer`, `client-state`, `forms`, `tailwind-v4` | написаны под этот проект, все примеры кода проверены компиляцией на этом стеке |

Прочитай `CLAUDE.md` и description каждого скила, чтобы знать, когда какой применять.

Обновлять официальные скилы (только по просьбе пользователя):

```bash
npx skills@1.7.0 add shadcn/ui -s shadcn -a claude-code -y --copy
```

Сторонние скилы не устанавливать.

## 5. Git

```bash
git init
git add -A
git commit -m "chore: project skeleton"
```

В репозиторий ОБЯЗАТЕЛЬНО входят: `package-lock.json`, `openapi.json`, `src/client/`, `src/routeTree.gen.ts`, `public/mockServiceWorker.js`, `.claude/`, `CLAUDE.md`, `skills-lock.json`. Без `src/routeTree.gen.ts` сборка на свежем клоне падает (`tsc -b` запускается раньше, чем плагин роутера его создаёт).

## 6. Когда появится настоящая схема бэкенда

Сейчас `openapi.json` — пример (эндпоинты login / services / orders), чтобы проект собирался. Когда бэкендер поднимет FastAPI:

```bash
curl -o openapi.json http://<IP-бэкенда>:8000/openapi.json
npm run gen
npm run typecheck
```

Для dev-прокси на его машину: `API_PROXY_TARGET=http://<IP>:8000 npm run dev`. Подробности — скил `api-layer`.

## 7. Отчёт пользователю

Коротко: версия Node, результат каждой команды из шагов 1–3, список скилов из шага 4, хэш первого коммита. Если что-то не прошло — точный текст ошибки и что ты НЕ стал делать.

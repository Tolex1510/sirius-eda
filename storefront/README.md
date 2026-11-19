# SSR-витрина Сириус.Еды — ЛР №8

Next.js App Router, TypeScript, Tailwind CSS 4 и нативный fetch.
Публичное меню выполняется на сервере; кабинеты и оформление остаются в `../frontend`.
Дизайн сохранён в цветах существующего приложения, шаблон методички не требуется.

## Локальный запуск

Нужен Node.js 20.9+; проверено на Node.js 24.13.1. FastAPI должен быть запущен.

```bash
cd storefront
cp .env.example .env.local
npm ci
npm run dev
```

Адрес: http://localhost:3001/menu. Порт 3000 занят Grafana.
В `.env.local` задайте `API_INTERNAL_URL` — адрес FastAPI без `/api` в конце.
`CABINET_URL` задаёт адрес существующего приложения с оплатой и заказами.
Для production-проверки:

```bash
npm run build
npm start
```

Проверочные запуски сбрасывают только свой runtime-кеш Next для воспроизводимости ошибки на некешированной странице.

Production-сборка не требует работающего API: HTML меню и карточек создаётся при первом запросе,
затем кешируется на 60 секунд. `npm start` запускает standalone-сервер и копирует static/public.
Остановка — Ctrl+C. Секретные ключи ЮKassa и JWT во фронтенд не передаются.

## Docker

Из корня проекта:

```bash
docker compose -p sirius-eda up -d --build
```

Общий nginx отдаёт `/menu`, `/menu/[id]`, `/menu-csr` и `/_next/*` из сервиса
`storefront`, `/api/*` — из FastAPI, остальные маршруты — из прежнего SPA.
Открыть http://localhost:8080/menu. Старое меню с поиском остаётся на `/`.
Переход «Выбрать порции и заказать» открывает форму оформления выбранного блюда в SPA.

## Как устроены требования

| Требование | Реализация |
| --- | --- |
| SSR/ISR `/menu` | `src/app/menu/[[...listing]]/page.tsx`, серверный компонент |
| SSR/ISR `/menu/[id]` | `src/app/menu/[id]/page.tsx`, `await params` |
| REST | `src/lib/api.ts`: server-only, fetch, таймаут 5 секунд |
| Карточки | `src/components/FoodCard.tsx` |
| Загрузка | `src/app/menu/loading.tsx` |
| Ошибка и повтор | `src/app/menu/error.tsx`, reset + router.refresh |
| Отсутствующее блюдо | `src/app/menu/not-found.tsx`, notFound() |
| SEO | root metadata и generateMetadata блюда: title, description, Open Graph, canonical |
| ISR | `revalidate = 60` на обеих страницах и `next.revalidate = 60` у fetch |
| CSR | `/menu-csr`, клиентский useEffect и fetch с cache: no-store |
| SSR/CSR-замеры | `scripts/verify.mjs`, результаты в `../docs/lab8/results/` |

Необычное имя `[[...listing]]` нужно для генерации страницы `/menu` по первому запросу
через `generateStaticParams() { return [] }`, без API во время Docker build.
Маршрут принимает только пустой listing; произвольные вложенные пути возвращают notFound().
Отдельный `[id]` обрабатывает карточки блюд. Это не меняет требуемые URL.

SSR здесь — серверное получение данных и HTML с блюдами; ISR добавляет повторное
использование готового HTML. Next Data Cache и готовые страницы — другой уровень
кеша, чем Redis в FastAPI. После 60 секунд первый запрос может получить старый HTML,
пока Next обновляет его в фоне. Следующий запрос показывает новую цену.
Если API не работает, уже закешированные страницы могут продолжать открываться.
Для демонстрации ошибки открыть ранее не запрошенный `/menu/<id>`.

## Автоматическая проверка

Установить Python-зависимости проекта и Chromium для Playwright. Скрипт требует
свободные порты 3001 и 8092, production-сборку; обычные dev/start процессы перед ним остановить.

```bash
npm run build
node scripts/verify.mjs
node scripts/verify.mjs --isr-only
node scripts/verify-handoff.mjs
```

Если Chromium установлен нестандартно, задайте `PLAYWRIGHT_CHROMIUM_EXECUTABLE`.
Скрипт сам поднимает production Next.js и настоящий FastAPI с изолированными
in-memory репозиториями, затем останавливает оба процесса. Рабочая БД не используется.
Первый запуск проверяет HTML, метаданные, отсутствие блюд в CSR-HTML, реальную остановку API,
повтор после восстановления, loading, мобильную ширину. Второй отдельно проверяет ISR со сменой цены 190 → 197.
Смена цены выполняется через настоящий PATCH с тестовой авторизацией.
Проверка ISR занимает больше минуты. Третий запуск проверяет открытие выбранного блюда
в настоящем Vite SPA по ссылке `/?item=1`, без создания платежа. Он использует порт 5174.
Для него нужны зависимости `frontend` (`cd ../frontend && npm ci`).

Для замеров используется Chromium и Chrome DevTools Protocol: Network.setCacheDisabled,
Network.emulateNetworkConditions, по три новых browser context на SSR и CSR.
Задержка сети 80 мс, download 200000 B/s, upload 100000 B/s. Искусственная задержка
API в сценарии loading выключается до замеров. Серверный кеш ISR прогрет; браузерный отключён.
`dish_ms` — момент появления первого непустого видимого блока блюда в DOM, не время доставки заказа.
`fcp_ms` — первая отрисовка любого содержимого страницы, включая шапку.
`ttfb_ms` — performance navigation responseStart. Локальные цифры не являются production SLA.

## Ручная проверка в Chrome DevTools

1. Открыть Network → Disable cache, выбрать одинаковые условия сети.
2. Трижды открыть `/menu` полным переходом, затем трижды `/menu-csr`.
3. Для SSR блюда уже есть в ответе Document/Ctrl+U, браузер не запрашивает меню из API.
4. Для CSR исходный Document не содержит блюд, после JS виден Fetch `/api/menu/items`.
5. Для ISR изменить цену через авторизованный PATCH `/menu/items/{id}`, сразу проверить старую,
   через 60 секунд запросить страницу и дождаться фонового обновления новым запросом.
6. Для ошибки остановить FastAPI, открыть некешированную карточку, вернуть API и нажать повтор.

Результаты измерений и выводы приведены в корневом README и `../docs/lab8/RESULTS.md`.
Официальные материалы: [ISR](https://nextjs.org/docs/app/guides/incremental-static-regeneration),
[error handling](https://nextjs.org/docs/app/getting-started/error-handling),
[metadata](https://nextjs.org/docs/app/getting-started/metadata-and-og-images).

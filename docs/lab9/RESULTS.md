# ЛР №9: Observability — результаты

## Реализовано

- HTTP middleware принимает только безопасный `X-Correlation-ID` длиной до 128 символов; иначе создаёт UUID. ID возвращается ответом и присутствует в JSON-логе завершения запроса.
- ID сохраняется в строке заказа, поэтому `POST /orders/create` и отдельное подтверждение оплаты могут быть связаны одной бизнес-корреляцией.
- При записи события в outbox ID добавляется в payload; relay передаёт его в RabbitMQ `X-Correlation-ID`. Consumer кухни восстанавливает контекст и пишет JSON-лог с тем же значением.
- Если настроен OTLP endpoint, FastAPI и SQLAlchemy создают spans, relay создаёт producer span, consumer кухни продолжает trace из W3C `traceparent` и создаёт consumer span.
- `/metrics` публикует HTTP request count и duration histogram. Добавлены счётчик заказов и hit/miss/error cache. RabbitMQ plugin предоставляет метрики готовых сообщений очереди.
- Grafana автоматически получает Prometheus datasource и dashboard «Сириус.Еда — Observability». Существующий dashboard платежных webhook сохраняется.
- Sentry включается только при заданном `SENTRY_DSN`; в локальном режиме без DSN приложение работает обычно.

## Запуск для ручного показа

Стек запущен во время проверки. Для повторного запуска вместе с Prometheus, Grafana, Loki, Alloy и Jaeger:

```bash
cd /путь/к/sirius-eda
COMPOSE_PARALLEL_LIMIT=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317 \
  docker compose -p sirius-eda --profile monitoring up -d --build
```

Адреса:

- приложение: `http://localhost:8080`
- API metrics через nginx: `http://localhost:8080/api/metrics`
- Prometheus targets: `http://localhost:9090/targets`
- Grafana: `http://localhost:3000/d/sirius-observability`
- Jaeger: `http://localhost:16686`

Для Sentry положить DSN в локальный `.env` как `SENTRY_DSN=...`. DSN не коммитить. Для тестового маршрута задать `DEBUG=true` и войти администратором; маршрут `/debug/observability/error` намеренно закрыт ролью admin.

## Проверка 18.11.2026

| Проверка | Результат |
| --- | --- |
| Локальные тесты | 316 passed, 8 skipped, 1 предупреждение Starlette |
| Контейнеры | Все сервисы запущены; API, web, storefront, DB, Redis, RabbitMQ healthy |
| Correlation ID | Корректный ID возвращается; пробелы и длина 129 заменяются UUID |
| Заказ | №6332 создан и оплачен через API, correlation_id `demo-42-lab9-20261118` сохранён в БД |
| Кухня | `event_processed`, талон №1284, тот же correlation ID |
| Prometheus | `prometheus`, `rabbitmq`, `sirius-api` — UP |
| HTTP и бизнес-метрики | POST /orders/create: 1; orders_created: 1; cache hit: 1; HTTP p95: 0.095 с в момент снимка |
| Очередь | kitchen_queue ready: 0 — consumer обработал сообщение |
| Grafana | Dashboard загружен, 7 панелей; источники доступны через API Grafana |
| Loki | По correlation ID найдены JSON-логи кухни через datasource Grafana |
| Jaeger | Trace `42176a1e985daf7599f8c0d91267c61c`: API + SQL → outbox producer → kitchen/delivery consumers |
| Sentry | DSN подключён; RuntimeError отправлен с correlation ID, ingestion HTTP 200 |

Первый заказ №6331 был отменён сагой с причиной «Нет свободного курьера». Для успешного повторного сценария создан отдельный учебный курьер `lab9-courier@sirius.test`. Проверка не обращалась к ЮKassa: использован путь оплаты внутренним балансом тестового пользователя `lab9-observability@sirius.test`.

Исправлены проблемы, обнаруженные при реальном запуске: SQLAlchemy ограничен веткой 2.0 для OTel; Instrumentator обновлён до 8.1 для новой маршрутизации FastAPI; включены per-object метрики RabbitMQ; бизнес-счётчик охватывает checkout. Для classic Docker builder в командах указан COMPOSE_PARALLEL_LIMIT=1, чтобы несколько сервисов не собирали один image одновременно.

Артефакты: [pytest](results/pytest.txt), [targets](results/targets.json), [метрики](results/metrics.json), [JSON-логи](results/correlation.jsonl), [Loki](results/loki-kitchen.json), [spans Jaeger](results/trace.json). Проверки Grafana/Jaeger выполнены через HTTP API; визуальный просмотр панелей в браузере отдельно не проводился. Метрики — снимок короткого учебного прогона, не нагрузочный бенчмарк.

## Sentry: проверка DSN

API пересоздан с DSN из локального .env. Через TestClient внутри контейнера вызван настоящий admin-only маршрут приложения `/debug/observability/error` с JWT администратора. Получен ожидаемый HTTP 500. SDK сформировал RuntimeError и отправил envelope; сервер Sentry ответил HTTP 200.

- Event ID: `d1940b37e8024a37aa30bd35bd21ffb6`.
- Тег: `correlation_id=sentry-demo-9-20261118-fixed`.
- Артефакт без DSN: [sentry.json](results/sentry.json).

При проверке исправлена потеря тега: используется isolation scope запроса, созданный SDK, без дополнительной вложенной области. Веб-интерфейс Sentry нужно открыть и показать событие на защите; транспортное принятие подтверждено. Порядок — в [памятке защиты](DEFENSE.md).

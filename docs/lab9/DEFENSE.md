# ЛР №9: сценарий защиты

## Подготовка

```bash
COMPOSE_PARALLEL_LIMIT=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317 \
  docker compose -p sirius-eda --profile monitoring up -d --build
docker compose -p sirius-eda --profile monitoring ps
```

Показать `http://localhost:9090/targets`: `sirius-api`, `rabbitmq` и `prometheus` должны быть `UP`.
Открыть Grafana dashboard `http://localhost:3000/d/sirius-observability` и Jaeger `http://localhost:16686`.

## Сквозная корреляция

Нужен тестовый пользователь с JWT. Создать заказ через `POST /api/payments/checkout` либо `/api/orders/create`, отправив `X-Correlation-ID: demo-42`. После этого подтвердить тестовую оплату: только `OrderPaid` ставит заказ на кухню.

В двух терминалах найти логи:

```bash
docker compose -p sirius-eda logs --no-color --no-log-prefix api | jq 'select(.correlation_id == "demo-42")'
docker compose -p sirius-eda logs --no-color --no-log-prefix kitchen | jq 'select(.correlation_id == "demo-42")'
```

В Loki Explore использовать запрос:

```logql
{app="sirius-eda", service=~"api|kitchen"} |= "demo-42"
```

В Jaeger выбрать `sirius-api`, найти trace после подтверждения оплаты и показать HTTP span, SQL span, `rabbitmq.publish`, `rabbitmq.consume` и атрибут `app.correlation_id`.

## Метрики

Показать `http://localhost:8080/api/metrics`, затем дашборд:

- HTTP requests / s — `rate(http_requests_total[5m])`;
- latency p95 — histogram `http_request_duration_seconds_bucket`;
- 5xx — фильтр `status=~"5.."`;
- queue ready — `rabbitmq_queue_messages_ready{queue="kitchen_queue"}`;
- cache hit rate — метрика `sirius_cache_operations_total`;
- число заказов — `sirius_orders_created_total`.

## Sentry (дополнительный балл)

Задать `SENTRY_DSN` в локальном `.env`, включить `DEBUG=true`, пересоздать API. Войти администратором и вызвать `GET /api/debug/observability/error` с `X-Correlation-ID: sentry-demo-9`. Показать exception и тег `correlation_id` в тестовом проекте Sentry. После демонстрации отключить DEBUG.

Jaeger подтверждён прогоном 18.11.2026 (см. RESULTS.md). Sentry принял тестовую ошибку с correlation ID; Event ID указан в RESULTS.md.

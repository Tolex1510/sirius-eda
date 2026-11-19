# ЛР №9: Observability — оценка требований

Методичка: `Практики/Практическая работа № 9.docx`.

## Что уже было до ЛР №9

- Grafana, Loki и Alloy собирали журнал платёжных webhook.
- Приложение и RabbitMQ уже работали через Docker Compose.
- Сквозного correlation ID, Prometheus scrape и распределённых trace не было.

## Что добавлено в текущем проходе

| Требование | Где реализовано |
| --- | --- |
| Принимать `X-Correlation-ID`, проверять формат, иначе генерировать ID и возвращать его в ответе | `app/core/observability.py`, middleware FastAPI |
| Хранить ID с заказом, чтобы он переживал отдельный запрос оплаты | `app/models.py`, `app/domain/entities.py`, миграция `0012_order_correlation_id.py` |
| Передавать ID и `traceparent` в событии через outbox и заголовки RabbitMQ | `app/outbox.py`, `app/core/rabbitmq.py`, `app/workers/consumer.py` |
| JSON-логи в stdout с временем, уровнем, именем сервиса и контекстом | `app/core/observability.py`; конфигурация подключается API, consumer'ами, outbox и gRPC |
| RED HTTP-метрики | `prometheus-fastapi-instrumentator`, endpoint `/metrics` |
| Бизнес-метрика количества заказов и hit/miss/error кеша | `app/core/observability.py`, `app/modules/orders/service.py`, `app/core/cache.py` |
| Метрики очереди RabbitMQ | `rabbitmq_prometheus`, включён через `deploy/rabbitmq/enabled_plugins` |
| Prometheus и его scrape-конфигурация | Compose profile `monitoring`, `deploy/monitoring/prometheus.yml` |
| Grafana-панели и просмотр логов | `deploy/monitoring/grafana/dashboards/observability.json`; Loki продолжает показывать webhook |
| OTel FastAPI/SQLAlchemy, producer/consumer spans, OTLP в Jaeger | `app/core/observability.py`, `app/core/rabbitmq.py`, `app/workers/consumer.py`, Compose profile `monitoring` |
| Sentry с тегом correlation ID | Подключение по `SENTRY_DSN`; для безопасной демонстрации ошибки есть admin-only маршрут при `DEBUG=true` |

## Проверка 18.11.2026

Локальные тесты: 316 passed, 8 skipped. Проверены correlation ID и его валидация, JSON-логи API/кухни, сбор логов Loki, загрузка семи панелей Grafana и общий trace HTTP → outbox → RabbitMQ → кухня в Jaeger. Найденные несовместимости зависимостей исправлены в requirements.txt; для метрик очереди включён per-object режим RabbitMQ.

Sentry: DSN подключён, ошибка с correlation ID принята сервером (HTTP 200). Веб-интерфейс для показа события на защите открывается отдельно. Подробные результаты — в RESULTS.md.

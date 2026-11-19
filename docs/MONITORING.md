# Уведомления об оплате в Grafana

## Дашборд ЛР №9

Профиль `monitoring` также добавляет Prometheus, RabbitMQ exporter и Jaeger. Дашборд Observability: `http://localhost:3000/d/sirius-observability`; targets Prometheus: `http://localhost:9090/targets`; Jaeger: `http://localhost:16686`.

```bash
COMPOSE_PARALLEL_LIMIT=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317 \
  docker compose -p sirius-eda --profile monitoring up -d --build
```

API публикует `/metrics`, доступный через nginx как `http://localhost:8080/api/metrics`. RabbitMQ `rabbitmq_prometheus` отдаёт метрики внутри Compose-сети на `rabbitmq:15692`. В Grafana используются Prometheus и Loki data sources.

Методика correlation ID и трассировки: [сценарий защиты ЛР №9](lab9/DEFENSE.md). Dashboard платежей и прежняя инструкция ниже сохранены.

Открыть http://localhost:3000/d/sirius-payments — дашборд «Платёжные уведомления».
Для просмотра вход не требуется (анонимный Viewer). Локальный администратор:
`admin`, пароль из `GRAFANA_ADMIN_PASSWORD` (по умолчанию `sirius-local-admin`).
Grafana опубликована только на localhost; Loki и Alloy наружу не опубликованы.

Запуск в своей WSL:

```bash
docker compose -p sirius-eda --profile monitoring up -d loki alloy grafana
```

Для текущего учебного стенда:

```bash
docker compose --env-file /tmp/sirius-qa.env -p sirius-practice --profile monitoring up -d loki alloy grafana
```

Сборщик автоматически ограничен текущим Compose-проектом и сервисами API, webhook, кухни, доставки, заказов, платежей и outbox.
Alloy читает Docker API через сокет Docker; профиль предназначен для локального учебного стенда.

## Что показывается

- Число уведомлений, обработанных запросов, ошибок и неизвестных объектов за выбранный период.
- График входящих типов событий: `payment.succeeded`, `payment.canceled`, `refund.succeeded`.
- Таблица: время, входящий тип, номер заказа, фактические статусы платежа и возврата,
  результат обработки, HTTP-код, длительность и ID объекта провайдера.
- Исходные HTTP-запросы внизу: там видны и обращения до добавления структурированного журнала.

Дашборд обновляется каждые 5 секунд. Можно выбрать период справа вверху;
поле номера заказа принимает номер или `.*` для всех. Фильтр заказа применяется
к таблице и счётчикам; нижний журнал HTTP всегда показывает все входящие обращения.
Если таблица пуста, сбросьте номер заказа на `.*` и увеличьте период.

`processed` означает, что объект найден и сверка с API провайдера выполнена.
Это не означает, что входящее утверждение о платеже совпало с действительностью:
например, событие `payment.succeeded` может сопровождаться фактическим статусом `pending`.
`ignored` — объект не найден в нашей базе; `failed` — обработка завершилась ошибкой.
Повторные доставки видны отдельными строками, а идемпотентность бизнес-операций сохраняется.
Ошибки валидации до входа в обработчик (422) видны в нижнем HTTP-журнале.
Неудачный вызов API не показывает статус/заказ как проверенные, эти поля остаются пустыми.

Полные тела, ключи, платёжные реквизиты и тексты ошибок провайдера не логируются.
Журнал не доказывает происхождение отправителя: статус проверяется отдельным запросом
к API ЮKassa. Исторические тела старых webhook восстановить из access-логов нельзя.

## Где код

- `app/modules/payments/router.py`: запись результата каждого валидного webhook, включая ошибки.
- `app/modules/payments/service.py`: поиск платежа и сверка через API провайдера.
- `app/modules/payments/telemetry.py`: JSON-журнал с разрешёнными полями.
- `deploy/monitoring/config.alloy`: чтение логов контейнеров и отправка в Loki.
- `deploy/monitoring/loki.yaml`: локальное хранение и срок хранения 7 дней.
- `deploy/monitoring/grafana/`: источник Loki, автоматическая загрузка дашборда и его JSON.
- `docker-compose.yml`: профиль `monitoring`, хранилища для Loki, Alloy и Grafana.

Данные сохраняются после перезапуска контейнеров. По умолчанию используются named volumes.
На текущей машине системный раздел Docker заполнен, поэтому в локальном `.env`
хранилища перенесены на раздел проекта:

```dotenv
LOKI_STORAGE=./.local/monitoring/loki
GRAFANA_STORAGE=./.local/monitoring/grafana
ALLOY_STORAGE=./.local/monitoring/alloy
```

Каталоги созданы заранее и доступны пользователям контейнеров; `.local/` исключён из Git.
Для такого же размещения создайте каталоги до запуска:

```bash
mkdir -p .local/monitoring/{loki,grafana,alloy}
chmod 1777 .local/monitoring/{loki,grafana,alloy}
```

Loki выполняет удаление асинхронно.
Удаление используемых volumes или каталогов хранилища удалит историю. Восстановление старых логов ограничено
тем, какие логи ещё доступны в Docker. На загруженном стенде нужна ротация контейнерных логов.

## Проверка вручную

1. Открыть дашборд и выбрать последние 15 минут.
2. Оплатить новый заказ в тестовом магазине ЮKassa с настроенным актуальным webhook URL.
3. Увидеть HTTP 200 в нижнем журнале и `payment.succeeded` в таблице.
4. При отмене дождаться строки `refund.succeeded` и фактического возврата `succeeded`.

Ручная повторная отправка сохранённого события тоже появится отдельной строкой;
она проверяет тракт сбора логов, но не является новым уведомлением от ЮKassa.

Официальные источники:
[Docker-логи в Alloy](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.docker/),
[локальная установка Loki](https://grafana.com/docs/loki/latest/setup/install/docker/),
[Grafana в Docker](https://grafana.com/docs/grafana/latest/setup-grafana/configure-docker/).

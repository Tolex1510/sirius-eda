# Платёжная интеграция: памятка для сдачи

## Что сказать в начале

> В проекте реализован трек D: интеграция с тестовой ЮKassa, идемпотентное создание платежа,
> обработка уведомлений, повторы при сетевых сбоях и Saga с возвратом при отмене заказа.
> Заказ и платёж имеют разные состояния. Денежные значения в БД хранятся в Numeric,
> расчёты нового платёжного сценария выполняются через Decimal.
> При оплате событие OrderPaid записывается в outbox той же транзакцией, что и состояние заказа.

Один веб-заказ в первой версии содержит одно блюдо и количество.
Реальные банковские деньги не используются: выбран тестовый магазин, ответы платежного API проверяются на `test=true`.

## Карта кода: что открывать преподавателю

| Что показать | Файл и точка входа | Что объяснить |
|---|---|---|
| Входной запрос оплаты | [router.py:27](../../app/modules/payments/router.py#L27), `StartPayment`; `create` около строки 73 | Принимаются order_id, amount и заголовок Idempotency-Key; сумма обязательна и имеет не более двух десятичных знаков |
| Бизнес-сценарий | [service.py:28](../../app/modules/payments/service.py#L28), `PaymentService.create` | Сначала сохраняется намерение платежа, затем вызывается шлюз; повтор возвращает ту же операцию |
| Проверка суммы и конкурентных запросов | [repository.py:44](../../app/modules/payments/repository.py#L44), `reserve` | Заказ блокируется FOR UPDATE; клиентская сумма сравнивается с серверной; проверяются ключ и наличие платежа |
| Ограничения на уровне БД | [models.py:245](../../app/models.py#L245), `Payment` | Уникальны order_id, gateway_id и пара user_id + idempotency_key; деньги Numeric(14,2) |
| HTTP-клиент ЮKassa | [gateway.py:15](../../app/modules/payments/gateway.py#L15), `_request`, `create`, `fetch`, `refund` | HTTP Basic Auth; постоянный ключ запроса; таймаут 10 секунд; разделение временных и окончательных ошибок |
| Webhook | [router.py:78](../../app/modules/payments/router.py#L78), `webhook` | Три события провайдера направляются в соответствующие сценарии; успешный ответ — HTTP 200 |
| Проверка подлинности | [service.py:58](../../app/modules/payments/service.py#L58), `webhook`, `refund_webhook`, `_apply` | Тело запроса не доказывает оплату: объект перечитывается через API, сверяются сумма, валюта и заказ |
| Подтверждение оплаты | [repository.py:87](../../app/modules/payments/repository.py#L87), `apply` | Только первый переход в succeeded меняет заказ на paid и создаёт OrderPaid |
| Отмена заказа | [repository.py:119](../../app/modules/payments/repository.py#L119), `cancel` | Отмена и OrderCancelled сохраняются одной транзакцией; прямого HTTP-вызова refund здесь нет |
| Consumer саги | [payments_consumer.py:14](../../app/workers/payments_consumer.py#L14), `on_order_cancelled` | Событие из RabbitMQ инициирует компенсацию платёжного модуля |
| Идемпотентность компенсации | [repository.py:137](../../app/modules/payments/repository.py#L137), `request_refund` | Inbox receipt и намерение возврата фиксируются атомарно; повтор не создаёт второй возврат |
| Возврат у провайдера | [gateway.py:56](../../app/modules/payments/gateway.py#L56), `refund` | Для создания — POST с refund-UUID; при сохранённом refund_id — GET состояния уже созданного возврата |
| Retry и DLQ | [tasks/payments.py:19](../../app/tasks/payments.py#L19), `sync_payment`; `PaymentSyncTask.on_failure` выше | Четыре повтора после первой попытки, паузы 1/2/4/8 секунд + jitter; после исчерпания — DLQ и review_required |
| Периодическая страховка | [maintenance.py:61](../../app/tasks/maintenance.py#L61), `reconcile_payments`; [celery_app.py:57](../../app/core/celery_app.py#L57) | Каждые 15 секунд подбираются незавершённые платежи и возвраты |
| Transactional Outbox / Inbox | [outbox.py:20](../../app/outbox.py#L20), `add_to_outbox`, `add_receipt`, `commit_once` | Данные, событие и отметка обработки связаны локальной транзакцией |
| Доставка событий | [outbox_relay.py:80](../../app/workers/outbox_relay.py#L80), `publish_pending` | Событие отмечается отправленным после подтверждения RabbitMQ; возможный повтор отсеивается получателем |
| Очередь платежей | [rabbitmq.py:35](../../app/core/rabbitmq.py#L35), `PAYMENTS` | payments_queue подписана на order.cancelled; есть отдельная payments_dlq |
| Автоматическая отмена при отказе доставки | [orders/service.py:91](../../app/modules/orders/service.py#L91), `compensate_failed_delivery` | DeliveryFailed приводит к OrderCancelled, далее возврат выполняет платёжный consumer |
| Интерфейс | [Checkout.tsx](../../frontend/src/components/checkout/Checkout.tsx), [Orders.tsx](../../frontend/src/pages/Orders.tsx), [OrderCard.tsx](../../frontend/src/components/orders/OrderCard.tsx) | Создание заказа, передача суммы и ключа, переход к провайдеру, отображение платежа и возврата |
| Публичный путь уведомлений | [deploy/webhook.conf](../../deploy/webhook.conf) | Снаружи разрешён только POST /api/payments/webhook, остальные страницы возвращают 404 |

Номера строк — ориентиры на момент подготовки памятки. Главный ориентир — название метода.

## Как проходит оплата

```mermaid
sequenceDiagram
    participant U as Браузер
    participant API as Payments API
    participant DB as PostgreSQL
    participant G as ЮKassa
    participant Q as RabbitMQ
    participant K as Кухня
    participant D as Доставка
    U->>API: POST /payments (order_id, amount, Idempotency-Key)
    API->>DB: Проверка заказа + сохранение намерения
    API->>G: Создать платёж с постоянным ключом
    G-->>API: confirmation_url
    API-->>U: Ссылка на оплату
    U->>G: Тестовая оплата
    G->>API: payment.succeeded
    API->>G: GET платежа для проверки
    API->>DB: payment=succeeded, order=paid, OrderPaid в outbox
    DB->>Q: Релей отправляет событие
    Q->>K: OrderPaid
    Q->>D: OrderPaid
```

Внешний путь `/api/payments` проксируется в FastAPI `/payments`.
Возвращение браузера со страницы оплаты не считается подтверждением.
При пропавшем webhook состояние восстановит периодическая сверка.

## Идемпотентность: три уровня

1. **Наш HTTP API.** Одинаковые user_id, order_id, amount и ключ дают тот же id платежа.
   Другой ключ того же заказа или изменённая сумма приводят к конфликту. FOR UPDATE и уникальные ограничения
   защищают и от одновременных запросов, а не только от последовательного двойного клика.
2. **API ЮKassa.** Ключом провайдера служит сохранённый UUID платежного намерения.
   Он может отличаться от клиентского ключа, но не меняется при повторах.
   Возврат использует отдельный постоянный ключ `refund-UUID`.
3. **События и конечные эффекты.** processed_events имеет ключ consumer + event_id.
   При обработке OrderCancelled отметка и refund_status=pending сохраняются вместе.
   Даже логически та же отмена с новым event_id не создаст новый refund, если он уже запрошен.

Webhook повторно проверяет объект у провайдера. Повторное succeeded не создаёт ещё один OrderPaid,
а запоздавшее pending не откатывает уже подтверждённую оплату.

Формулировка для ответа:

> Доставка сообщений допускает повторения. Мы обеспечиваем однократный бизнес-эффект,
> используя состояние, ограничения БД, Inbox и идемпотентный ключ внешней операции.

## Saga: что именно компенсируется

```text
OrderPaid
   ↓
Доставка: нет свободного курьера
   ↓ DeliveryFailed
Заказы: cancelled + OrderCancelled в outbox
   ↓ RabbitMQ → payments_queue
Payments consumer: Inbox + refund_status=pending
   ↓ Celery
ЮKassa: refund с постоянным ключом
   ↓
refund_status=succeeded
```

Сага реализована хореографией: компоненты реагируют на события, общего координатора распределённой
транзакции нет. Возврат — отдельная компенсирующая операция, а не SQL rollback банковского списания.
После возврата платёж остаётся succeeded, заказ — cancelled, состояние возврата — succeeded.
Деньги внешней оплаты не зачисляются на внутренний баланс.

Обычная отмена клиентом тоже публикует OrderCancelled. Если оплата подтвердилась после отмены,
сохраняется новое событие отмены, чтобы компенсация не потерялась.

## Повторы и два вида DLQ

| Механизм | Для чего | Где смотреть |
|---|---|---|
| RabbitMQ | Доменные события OrderPaid, DeliveryFailed, OrderCancelled | payments_queue / payments_dlq и другие очереди |
| Celery с Redis | Фоновые обращения к шлюзу и сверка результатов | default / dlq |

HTTP 5xx, таймауты и 429 считаются временными. Окончательные 4xx не повторяются как сетевой сбой.
После исчерпания попыток ставится review_required; успешная оплата не превращается в failed только из-за таймаута проверки.

## Команды на текущей машине

Здесь стенд запущен с отдельной конфигурацией и именем проекта. Эти команды читают состояние:

```bash
docker compose --env-file /tmp/sirius-qa.env -p sirius-practice logs --tail=100 api payments worker outbox
docker compose --env-file /tmp/sirius-qa.env -p sirius-practice exec api python -m app.cli outbox-status
docker compose --env-file /tmp/sirius-qa.env -p sirius-practice exec api python -m app.cli events-dlq
docker compose --env-file /tmp/sirius-qa.env -p sirius-practice exec api python -m app.cli dlq-list
```

После устранения причины сбоя можно вернуть сообщения в работу:

```bash
docker compose --env-file /tmp/sirius-qa.env -p sirius-practice exec api python -m app.cli events-dlq-replay --queue payments
docker compose --env-file /tmp/sirius-qa.env -p sirius-practice exec api python -m app.cli dlq-replay
```

В WSL при запуске по README используется `docker compose -p sirius-eda` и собственный `.env`.
Не показывайте секретный ключ на защите: достаточно `.env.example` и `.gitignore`.

## Какие тесты запускать на защите

```bash
.venv/bin/python -m pytest tests/test_payments.py tests/test_payment_methodic.py -q
# С настоящим тестовым RabbitMQ:
RABBITMQ_TEST_URL=amqp://sirius:sirius@localhost:55672/ \
.venv/bin/python -m pytest tests/test_payment_saga_rabbitmq.py -q
```

| Пункт | Где находится тест |
|---|---|
| Обязательная сумма, подмена суммы, повтор POST | tests/test_payment_methodic.py:76 |
| Поддельный и повторный webhook | tests/test_payment_methodic.py:96 |
| Неуспешная оплата insufficient_funds | tests/test_payment_methodic.py:112 |
| Webhook возврата и дубли | tests/test_payment_methodic.py:127 |
| Дубли OrderCancelled | tests/test_payment_methodic.py:152 |
| Нельзя вернуть активный чужой/неотменённый заказ | tests/test_payment_methodic.py:170; tests/test_payments.py:102 |
| Потерянный ответ шлюза, тот же ключ | tests/test_payment_methodic.py:186 |
| Повторы, DLQ и ручная проверка | tests/test_payment_methodic.py:203 |
| Потеря постановки задачи после записи в БД | tests/test_payment_methodic.py:226 |
| Поздняя оплата отменённого заказа | tests/test_payments.py:128 |
| Три копии события через настоящий RabbitMQ → один refund | tests/test_payment_saga_rabbitmq.py:17 |

Текущая профильная проверка: **36 passed**. Последний полный прогон: **320 passed**.

## Доказательства, которые уже сохранены

- `results/yookassa_saga_refund.json`: заказ №108, возврат 290 ₽ подтверждён GET API ЮKassa,
  сохранён тот же refund_id; цепочка order.paid → delivery.failed → order.cancelled и обработчик payments.
- `results/yookassa_duplicate_webhook.json`: ручные повторы HTTPS webhook для заказа №106 сохранили один OrderPaid.
  Был временный ответ 503 при проверке провайдера, затем успешные повторы 200.
- `results/payment_probe_methodic.json`: 100 одинаковых запросов дали один платёж;
  100 разных заказов дали 100 платежей. Это demo-шлюз, не нагрузка на ЮKassa.
- `results/webhook_check_latest.json`: проверка актуального публичного адреса и маршрута webhook.

## Порядок показа за 5–7 минут

1. Показать сайт и успешную тестовую оплату.
2. Открыть router → service → repository → gateway и объяснить разделение слоёв.
3. Показать reserve, ограничения модели Payment и два одинаковых запроса в тесте.
4. Показать consumer OrderCancelled, request_refund и gateway.refund; привести реальный заказ №108.
5. Показать retry и on_failure, тест DLQ.
6. Показать входящий webhook и тест поддельного статуса, затем отчёт нагрузки и ADR.

## Что важно не перепутать

- Настроенный URL в кабинете ещё не доказывает получение уведомления от провайдера.
- Доступность HTTPS endpoint и ручное воспроизведение webhook — отдельные проверки.
- Для проверки автоматической доставки нужен новый тестовый платёж после настройки актуального URL.
- Бесплатный localhost.run меняет доменные имена. Docker переподключает туннель, но не может автоматически
  изменить настройки кабинета ЮKassa. Для постоянного стенда нужен стабильный HTTPS-адрес.
- ЮKassa использует payment.canceled вместо учебного payment_failed. Подлинность проверяется авторизованным
  запросом объекта к API, как допускает её протокол; вымышленной HMAC-подписи в коде нет.
- Новые платежи используют Decimal/Numeric. Старые DTO лабораторных местами остаются float ради совместимости.

Обоснование: [ADR платежей](../adr/001-external-payments.md).
Соответствие методичке: [TRACK_D_CHECKLIST.md](TRACK_D_CHECKLIST.md).

## Наблюдение за webhook в Grafana

Открыть http://localhost:3000/d/sirius-payments — «Платёжные уведомления».
Таблица показывает входящий event, заказ, проверенные статусы, HTTP-код и время обработки.
Внизу доступны исходные HTTP-запросы, включая старые уведомления от ЮKassa.
Сбор: stdout API → Alloy → Loki → Grafana. Полные тела и секреты не сохраняются.
Настройка и трактовка полей: [MONITORING.md](../MONITORING.md).
Первое заполнение таблицы проверено ручными повторами событий завершённого заказа №109;
это не новые уведомления от провайдера. Исходные автоматические запросы видны в HTTP-блоке.

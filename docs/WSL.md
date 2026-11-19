# Запуск Сириус.Еды в WSL 2

Это локальный стенд учебной практики: сайт, API, PostgreSQL/pgvector, Redis, RabbitMQ,
доставка, consumers, Celery и, по желанию, локальный AI.
Запуск модели на текущей машине для разработки не требуется.

## Подготовка

1. Установить WSL 2 и Ubuntu. Если WSL уже используется для Хоши, можно использовать существующий дистрибутив:
   проект и Compose-ресурсы будут отдельными.
2. В Docker Desktop включить WSL Integration для этого дистрибутива.
3. В терминале Ubuntu проверить `docker version` и `docker compose version`.
4. Перенести/клонировать репозиторий внутрь Linux-файловой системы, например `~/projects/sirius-eda`.
   Нужны актуальные изменения из этой работы; сам по себе старый remote их ещё не содержит.

Справка Docker: https://docs.docker.com/desktop/features/wsl/

## Первый запуск без модели и без ЮKassa

В каталоге проекта:

```bash
cp .env.example .env
```

В `.env` задать случайный `SECRET_KEY` длиной минимум 32 символа.
Если нужен набор тестовых аккаунтов, задать собственный `DEMO_PASSWORD` длиной минимум 8 символов.
Секретный ключ можно создать командой `openssl rand -hex 32`.

```bash
docker compose -p sirius-eda up -d --build
docker compose -p sirius-eda ps
docker compose -p sirius-eda logs --tail=50 init api
```

Открыть в браузере Windows: http://localhost:8080

Миграции и начальное меню выполняет одноразовый `init`.
Если меню уже заполнено лабораторными, оно сохраняется.
При заданном `DEMO_PASSWORD` создаются отсутствующие аккаунты:
`student@demo.sirius.ru`, `courier@demo.sirius.ru`, `cook@demo.sirius.ru`, `admin@demo.sirius.ru`.
Пароль берётся из `.env`. Повторный запуск не меняет пароли существующих аккаунтов.
Можно просто зарегистрироваться через сайт. При отсутствии свободного курьера сага отменит оплаченный заказ.

По умолчанию `PAYMENT_PROVIDER=demo`: демонстрационная оплата без банковской карты и списания денег.
AI без Ollama сообщает о недоступности. Остальные функции работают самостоятельно.

При занятых портах поменять `WEB_PORT`, `DB_PORT`, `REDIS_PORT`, `RABBITMQ_PORT`, `RABBITMQ_UI_PORT`.
При изменении порта сайта обязательно обновить `PUBLIC_URL`, например `http://localhost:8081`.
Браузерные сессии проверяют этот origin.

## Текущий стенд: Ollama уже работает у Хоши

Используем существующие Qwen 3B и BGE-M3 через Docker SSH-туннель, профиль `remote-ai`. Подробные команды, настройка SSH-agent и порядок восстановления после перезагрузки: [ASSISTANT.md](ASSISTANT.md). Второй экземпляр Ollama для этого варианта не запускается. Варианты ниже нужны для самостоятельного размещения моделей на одном компьютере с приложением.

## Вариант A: Ollama в том же Compose

В `.env`:

```dotenv
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:3b-instruct-q5_K_M
OLLAMA_EMBED_MODEL=bge-m3:latest
```

```bash
docker compose -p sirius-eda --profile ai up -d
docker compose -p sirius-eda exec ollama ollama pull qwen2.5:3b-instruct-q5_K_M
docker compose -p sirius-eda exec ollama ollama pull bge-m3:latest
docker compose -p sirius-eda up -d --force-recreate api worker
docker compose -p sirius-eda exec worker python -c 'from app.tasks.maintenance import index_assistant_knowledge; print(index_assistant_knowledge())'
```

Загрузка моделей выполняется отдельно и может занять время и место на диске.
Модели сохраняются в томе `ollama_data`, повторно скачивать их после перезапуска не нужно.
Qwen используется для текста, bge-m3:latest — только для эмбеддингов.
Индекс рассчитан на 1024 измерений. Замена embedding-модели требует совместимой размерности и переиндексации.

Если Qwen 3B работает медленно, заменить `OLLAMA_MODEL` на `qwen2.5:1.5b`, загрузить её
и пересоздать `api` и `worker`. Качество ответов оценивается после фактического запуска на компьютере.
Для генерации используются контекст 4096 и ограничение ответа 350 токенами.
Индекс обновляется периодически раз в 5 минут, первую индексацию удобнее запустить командой выше.

При поддерживаемой NVIDIA GPU можно использовать дополнительный файл:

```bash
docker compose -p sirius-eda -f docker-compose.yml -f docker-compose.gpu.yml --profile ai up -d
```

Поддержку GPU нужно проверить на конкретной машине. Без override Ollama работает без обязательного GPU.

## Вариант B: уже установленная Ollama на Windows

Модели загружаются командами `ollama pull qwen2.5:3b-instruct-q5_K_M` и `ollama pull bge-m3:latest` в Windows.
В `.env` оставить `OLLAMA_URL=http://host.docker.internal:11434`.
Ollama должна слушать интерфейс, доступный контейнерам: её `OLLAMA_HOST` задаётся в настройках среды Windows,
после чего приложение Ollama полностью перезапускается.
При привязке к `0.0.0.0:11434` ограничить входящие соединения средствами Windows Firewall локальным стендом.
Не запускать одновременно второй сервер Ollama из профиля `ai` на том же порту.

Проверка соединения из контейнера:

```bash
docker compose -p sirius-eda exec api python -c 'import httpx; print(httpx.get("http://host.docker.internal:11434/api/tags").status_code)'
```

Если используется Ollama непосредственно в WSL с собственным Docker Engine, адрес хоста может отличаться.
В таком случае проще использовать вариант A и адрес сервиса `ollama`.

## Подключение тестового магазина ЮKassa

1. Создать тестовый магазин и получить shop ID и тестовый ключ.
2. Указать в локальном `.env` `PAYMENT_PROVIDER=yookassa`, `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`.
3. Настроить внешний HTTPS-адрес для сайта/вебхука через туннель или свой reverse proxy.
   Указать этот адрес в `PUBLIC_URL`. Адрес должен открываться и у пользователя при возвращении с оплаты.
4. В кабинете ЮKassa указать `https://ВАШ-АДРЕС/api/payments/webhook` и события
   `payment.succeeded`, `payment.canceled`, `refund.succeeded`.
5. Пересоздать `api`, `worker`, `beat` и проверить полный цикл тестового платежа.

```bash
docker compose -p sirius-eda up -d --force-recreate api worker beat
```

Приложение принимает только объекты с `test=true`. Подлинность оплаты подтверждается запросом к API ЮKassa.
Платёж привязан к одному заказу. После окончательного отказа в этой версии оформляется новый заказ.
Не используйте ключи реального магазина.

## Обслуживание

```bash
docker compose -p sirius-eda logs -f api worker
docker compose -p sirius-eda exec api python -m app.cli dlq-list
docker compose -p sirius-eda exec api python -m app.cli dlq-replay
docker compose -p sirius-eda stop
docker compose -p sirius-eda start
```

Если задачи сверки исчерпали повторы, платёж помечается для ручной проверки, а задача уходит в DLQ.
После устранения причины replay запускает её заново. За пределами окна идемпотентности запросы создания
не повторяются автоматически: результат проверяется в кабинете провайдера.

Сайт и инфраструктура по умолчанию публикуют порты только на localhost.
Данные сохраняются в Docker volumes. Команды с удалением томов для обычного перезапуска не нужны.

## HTTPS webhook отдельно от сайта

В приложение добавлен отдельный ingress: он принимает только POST `/api/payments/webhook`,
не раскрывая меню, авторизацию и остальные API. Локальный порт — 8082, настраивается через `WEBHOOK_PORT`.

```bash
SIRIUS_PROJECT=sirius-eda scripts/webhook_tunnel.sh
```

Экспериментальный вариант — Localtunnel с выбранным поддоменом. На этом стенде после перезапуска имя оказалось недоступно; сервис остановлен, для сдачи пока не используйте его как постоянный адрес.
Задайте уникальное `WEBHOOK_SUBDOMAIN` в `.env`, затем:

```bash
docker compose -p sirius-eda --profile webhooks up -d --build webhook-localtunnel
docker compose -p sirius-eda logs --tail=5 webhook-localtunnel
```

Поле `webhook_url` содержит адрес для кабинета ЮKassa. Клиент запрашивает одно и то же имя
и отказывается от случайной замены, если оно занято. Бесплатный сервис не гарантирует
доступность или сохранение имени; для постоянного размещения нужен собственный HTTPS-домен.
Проверяйте внешний `/health` перед демонстрацией. Исходный клиент: https://github.com/localtunnel/localtunnel.

Альтернативный Docker-сервис с SSH-переподключением:

```bash
docker compose -p sirius-eda --profile webhooks up -d --build webhook-ssh
docker compose -p sirius-eda --profile webhooks logs webhook-ssh
```

В логах JSON-поле `address`/`tls` или строка с HTTPS покажет текущий адрес. Бесплатный URL временный:
при пересоздании соединения он может измениться, и адрес в кабинете ЮKassa нужно обновить.
Уже настроенный адрес сам по себе не делает туннель постоянным.

Скрипт `webhook_tunnel.sh` — альтернативный ручной запуск. Он поднимет `webhook-proxy` и подключит бесплатный SSH-туннель localhost.run.
В его выводе появится HTTPS-адрес. Указать в кабинете ЮKassa
`https://ВЫДАННЫЙ-АДРЕС/api/payments/webhook` и включить
`payment.succeeded`, `payment.canceled`, `refund.succeeded`.
Терминал с туннелем должен оставаться запущенным. После перезапуска адрес может измениться.
`PUBLIC_URL` сайта можно оставить localhost: webhook использует отдельный URL.

Альтернативный вариант при доступном исходящем порте 7844:

```bash
docker compose -p sirius-eda --profile webhooks up -d webhook-tunnel
docker compose -p sirius-eda --profile webhooks logs webhook-tunnel
```

Это временный Cloudflare Quick Tunnel. На текущей машине соединение с edge на 7844 блокируется сетью,
поэтому проверенный вариант для этого стенда — SSH-туннель.

Источники: https://localhost.run/docs/faq и https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/

Платёжная Saga теперь использует отдельный процесс `python -m app.workers.payments_consumer`:
OrderCancelled → payments_queue → атомарное намерение refund → Celery → шлюз.
В полном Compose процесс запускается автоматически. Для повторной доставки событий из его DLQ:

```bash
docker compose -p sirius-eda exec api python -m app.cli events-dlq-replay --queue payments
```

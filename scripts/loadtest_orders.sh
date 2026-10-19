#!/usr/bin/env bash
# Замер оформления заказов для README лабораторной № 5.
#   python -m app.cli load-users --count 50 > tokens.txt
#   ORDER_TASKS_MODE=sync   scripts/loadtest_orders.sh sync   tokens.txt
#   ORDER_TASKS_MODE=celery scripts/loadtest_orders.sh celery tokens.txt
# В режиме celery скрипт сам запускает воркер. Параметры: USERS (40), SPAWN_RATE (5),
# DURATION (2m), PORT (8000), WORKER_CONCURRENCY (64).
set -euo pipefail

LABEL=${1:?usage: scripts/loadtest_orders.sh <label> <tokens file>}
TOKENS=$(realpath "${2:?usage: scripts/loadtest_orders.sh <label> <tokens file>}")
USERS=${USERS:-40}
SPAWN_RATE=${SPAWN_RATE:-5}
DURATION=${DURATION:-2m}
PORT=${PORT:-8000}
WORKER_CONCURRENCY=${WORKER_CONCURRENCY:-64}
OUT=docs/lab5/results
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
mkdir -p "$OUT"

redis() { docker-compose exec -T redis redis-cli "$@"; }
pg() { docker-compose exec -T db psql -U sirius -d sirius_food -tAc "$1"; }

.venv/bin/uvicorn app.main:app --port "$PORT" --no-access-log --log-level warning &
SERVER=$!
WORKER=
SAMPLER=
trap 'kill $SERVER $WORKER $SAMPLER 2>/dev/null || true' EXIT

if [[ "${ORDER_TASKS_MODE:-}" == "celery" ]]; then
  redis DEL default > /dev/null
  # Задачи ждут внешние сервисы, а не CPU: потоки дешевле процессов.
  .venv/bin/celery -A app.core.celery_app worker --pool threads --concurrency "$WORKER_CONCURRENCY" \
    --loglevel warning > "$OUT/${LABEL}_worker.log" 2>&1 &
  WORKER=$!
fi
for _ in $(seq 50); do curl -sf "http://127.0.0.1:$PORT/menu/categories" >/dev/null && break; sleep 0.2; done

FIRST_ORDER=$(pg "select coalesce(max(id), 0) from orders")

# Каждые 2 секунды: load average и длина очереди Celery в Redis.
echo "time,load1,queue" > "$OUT/${LABEL}_system.csv"
(
  while true; do
    echo "$(date +%s),$(cut -d' ' -f1 /proc/loadavg),$(redis LLEN default | tr -d '\r')" >> "$OUT/${LABEL}_system.csv"
    sleep 2
  done
) &
SAMPLER=$!

LOCUST_TOKENS="$TOKENS" .venv/bin/locust -f locustfile_orders.py --host "http://127.0.0.1:$PORT" --headless \
  -u "$USERS" -r "$SPAWN_RATE" -t "$DURATION" \
  --csv "$OUT/$LABEL" --csv-full-history --html "$OUT/$LABEL.html" --only-summary

if [[ -n "$WORKER" ]]; then
  # Нагрузка снята, воркер дорабатывает очередь. Ждём, пока все задачи заказов завершатся.
  for _ in $(seq 300); do
    pending=$(pg "select count(*) from orders o where o.id > $FIRST_ORDER and
      (select count(*) from task_logs t where t.order_id = o.id and t.status in ('done', 'dead')) < 3")
    [[ "$pending" == "0" ]] && break
    sleep 1
  done
  pg "select count(*) as orders,
        round(percentile_cont(0.5) within group (order by seconds)::numeric, 2) as median_s,
        round(percentile_cont(0.95) within group (order by seconds)::numeric, 2) as p95_s,
        round(max(seconds)::numeric, 2) as max_s
      from (select o.id, extract(epoch from max(t.updated_at) - o.created_at) as seconds
            from orders o join task_logs t on t.order_id = o.id
            where o.id > $FIRST_ORDER group by o.id) s" > "$OUT/${LABEL}_receipts.txt"
  echo "orders|median_s|p95_s|max_s (время от заказа до последней задачи)"
  cat "$OUT/${LABEL}_receipts.txt"
fi

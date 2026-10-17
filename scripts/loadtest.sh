#!/usr/bin/env bash
# Замер для README: поднимает приложение, гоняет Locust и снимает метрики системы и PostgreSQL.
#   scripts/loadtest.sh before     до кеша
#   scripts/loadtest.sh after      после кеша
# Параметры: USERS (500), SPAWN_RATE (10), DURATION (3m), PORT (8000).
set -euo pipefail

LABEL=${1:?usage: scripts/loadtest.sh <label>}
USERS=${USERS:-500}
SPAWN_RATE=${SPAWN_RATE:-10}
DURATION=${DURATION:-3m}
PORT=${PORT:-8000}
OUT=docs/lab4/results
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
mkdir -p "$OUT"

pg() { docker-compose exec -T db psql -U sirius -d sirius_food -tAc "$1"; }
pg_counters() {
  # Чтение в SQLAlchemy заканчивается ROLLBACK, поэтому транзакции считаются вместе с откатами.
  pg "select xact_commit + xact_rollback, tup_returned, tup_fetched from pg_stat_database where datname = 'sirius_food'"
}

.venv/bin/uvicorn app.main:app --port "$PORT" --no-access-log --log-level warning &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; kill $SAMPLER 2>/dev/null || true' EXIT
for _ in $(seq 50); do curl -sf "http://127.0.0.1:$PORT/menu/categories" >/dev/null && break; sleep 0.2; done

# Каждые 5 секунд: load average, CPU контейнеров PostgreSQL и Redis, активные соединения к БД.
echo "time,load1,db_cpu,redis_cpu,db_connections" > "$OUT/${LABEL}_system.csv"
(
  while true; do
    load1=$(cut -d' ' -f1 /proc/loadavg)
    cpu=$(docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}' sirius-eda-db-1 sirius-eda-redis-1 | tr -d '%')
    db_cpu=$(awk '/db-1/ {print $2}' <<<"$cpu")
    redis_cpu=$(awk '/redis-1/ {print $2}' <<<"$cpu")
    conns=$(pg "select count(*) from pg_stat_activity where datname = 'sirius_food' and state = 'active'")
    echo "$(date +%s),$load1,$db_cpu,$redis_cpu,$conns" >> "$OUT/${LABEL}_system.csv"
    sleep 5
  done
) &
SAMPLER=$!

PG_BEFORE=$(pg_counters)
.venv/bin/locust -f locustfile.py --host "http://127.0.0.1:$PORT" --headless \
  -u "$USERS" -r "$SPAWN_RATE" -t "$DURATION" \
  --csv "$OUT/$LABEL" --csv-full-history --html "$OUT/$LABEL.html" --only-summary
PG_AFTER=$(pg_counters)

python3 - "$PG_BEFORE" "$PG_AFTER" > "$OUT/${LABEL}_postgres.txt" <<'PY'
import sys
names = ("transactions", "rows_returned", "rows_fetched")
before, after = ([int(v) for v in arg.split("|")] for arg in sys.argv[1:])
for name, b, a in zip(names, before, after):
    print(f"{name}={a - b}")
PY
cat "$OUT/${LABEL}_postgres.txt"

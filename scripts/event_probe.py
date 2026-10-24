"""
Замеры лабораторной № 7. Нужны запущенные API, релей и три consumer'а.

    PYTHONPATH=. python scripts/event_probe.py latency http://127.0.0.1:8000 notify
    PYTHONPATH=. python scripts/event_probe.py outage  http://127.0.0.1:8000 outage

latency: 200 заказов подряд оформляются и оплачиваются. Свободных курьеров 10,
остальные заказы проходят сагу. Время каждого шага берётся из БД: outbox_events и processed_events.
outage: RabbitMQ останавливается, 50 заказов оплачиваются, через 15 с брокер запускается.
Раз в 0,25 с пишется, сколько событий ждёт в outbox и сколько обработано.
"""
import csv
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
from sqlalchemy import text

from app.core.jwt import create_access_token
from app.database import engine

RESULTS = Path("docs/lab7/results")
STUDENT_ID = 9
COURIERS = 10
ORDERS = {"latency": 200, "outage": 50}
OUTAGE_SECONDS = 15
SAMPLE_SECONDS = 0.25


def sql(query: str, **params):
    with engine.begin() as connection:
        result = connection.execute(text(query), params)
        return result.all() if result.returns_rows else []


def free_couriers() -> None:
    """Десять курьеров без активных доставок: часть заказов назначается, остальные идут в сагу."""
    for number in range(1, COURIERS + 1):
        sql(
            "insert into users(email, balance, is_blocked, role_id) "
            "select :email, 0, false, id from roles where name = 'courier' on conflict (email) do nothing",
            email=f"probe-courier{number}@sirius.test",
        )
    sql(
        "update deliveries set status = 'completed' where status in ('in_progress', 'on_the_way') "
        "and courier_id in (select id from users where email like 'probe-courier%')"
    )


def place_orders(client: httpx.Client, count: int) -> list[tuple[int, float]]:
    placed = []
    for number in range(count):
        order_id = client.post("/orders/create", json={"item_id": number % 50 + 1, "quantity": 1}).json()["order_id"]
        started = time.perf_counter()
        response = client.post(f"/orders/{order_id}/pay")
        response.raise_for_status()
        placed.append((order_id, (time.perf_counter() - started) * 1000))
    return placed


def finished(order_ids: list[int]) -> int:
    """Сколько заказов прошли все шаги: кухня получила оплату, доставка назначена или заказ отменён и снят с кухни."""
    return sql(
        """
        select count(*) from orders o
        where o.id = any(:ids) and exists (
            select 1 from kitchen_tickets t where t.order_id = o.id
              and (o.status = 'paid' and exists (select 1 from deliveries d where d.order_id = o.id)
                   or o.status = 'cancelled' and t.status = 'cancelled')
        )
        """,
        ids=order_ids,
    )[0][0]


def wait_finished(order_ids: list[int], timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while finished(order_ids) < len(order_ids):
        if time.monotonic() > deadline:
            raise SystemExit(f"Обработано {finished(order_ids)} из {len(order_ids)} за {timeout} с")
        time.sleep(0.2)


def timings(order_ids: list[int]) -> dict[int, dict]:
    """Миллисекунды от записи OrderPaid в outbox до каждого шага."""
    rows = sql(
        """
        select (paid.payload->>'order_id')::int,
               extract(epoch from paid.published_at - paid.created_at) * 1000,
               extract(epoch from k.processed_at - paid.created_at) * 1000,
               extract(epoch from d.processed_at - paid.created_at) * 1000,
               extract(epoch from kc.processed_at - paid.created_at) * 1000
        from outbox_events paid
        join processed_events k on k.event_id = paid.event_id and k.consumer = 'kitchen'
        join processed_events d on d.event_id = paid.event_id and d.consumer = 'delivery'
        left join outbox_events c on c.routing_key = 'order.cancelled' and c.payload->>'order_id' = paid.payload->>'order_id'
        left join processed_events kc on kc.event_id = c.event_id and kc.consumer = 'kitchen'
        where paid.routing_key = 'order.paid' and (paid.payload->>'order_id')::int = any(:ids)
        """,
        ids=order_ids,
    )
    as_ms = lambda value: float(value) if value is not None else None
    return {
        order_id: {"relay_ms": as_ms(relay), "kitchen_ms": as_ms(kitchen), "delivery_ms": as_ms(delivery),
                   "saga_ms": as_ms(saga)}
        for order_id, relay, kitchen, delivery, saga in rows
    }


def summary(label: str, rows: list[dict]) -> None:
    for column in ("pay_ms", "relay_ms", "kitchen_ms", "delivery_ms", "saga_ms"):
        values = sorted(float(r[column]) for r in rows if r[column] not in (None, ""))
        if values:
            print(f"{label} {column}: n={len(values)} median={statistics.median(values):.1f} "
                  f"p95={values[int(len(values) * 0.95)]:.1f}")


def latency(client: httpx.Client, label: str) -> None:
    free_couriers()
    placed = place_orders(client, ORDERS["latency"])
    order_ids = [order_id for order_id, _ in placed]
    wait_finished(order_ids)
    steps = timings(order_ids)
    rows = [{"order_id": order_id, "pay_ms": f"{pay:.2f}", **steps[order_id]} for order_id, pay in placed]
    write(label, rows)
    assigned = sql("select count(*) from deliveries where order_id = any(:ids)", ids=order_ids)[0][0]
    print(f"{label}: {len(rows)} заказов, курьер назначен {assigned}, отменено сагой {len(rows) - assigned}")
    summary(label, rows)


def outage(client: httpx.Client, label: str) -> None:
    free_couriers()
    samples, stop = [], threading.Event()
    run_ids: list[int] = []
    started = time.monotonic()

    def sample():
        while not stop.is_set():
            pending = sql("select count(*) from outbox_events where published_at is null")[0][0]
            done = finished(run_ids) if run_ids else 0
            samples.append((round(time.monotonic() - started, 2), pending, done))
            time.sleep(SAMPLE_SECONDS)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    time.sleep(1)
    subprocess.run(["docker-compose", "stop", "rabbitmq"], check=True, capture_output=True)
    stopped_at = time.monotonic() - started
    placed = place_orders(client, ORDERS["outage"])
    run_ids.extend(order_id for order_id, _ in placed)
    time.sleep(max(0.0, OUTAGE_SECONDS - (time.monotonic() - started - stopped_at)))
    subprocess.run(["docker-compose", "start", "rabbitmq"], check=True, capture_output=True)
    started_at = time.monotonic() - started
    wait_finished(run_ids)
    done_at = time.monotonic() - started
    time.sleep(1)
    stop.set()
    sampler.join()

    with open(RESULTS / f"{label}_timeline.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seconds", "outbox_pending", "orders_finished"])
        writer.writerows(samples)
    with open(RESULTS / f"{label}_marks.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["event", "seconds"])
        writer.writerows([("rabbitmq_stopped", f"{stopped_at:.2f}"), ("rabbitmq_started", f"{started_at:.2f}"),
                          ("all_finished", f"{done_at:.2f}")])
    write(label, [{"order_id": order_id, "pay_ms": f"{pay:.2f}", **timings(run_ids).get(order_id, {})}
                  for order_id, pay in placed])
    pays = sorted(pay for _, pay in placed)
    lost = len(run_ids) - finished(run_ids)
    print(f"{label}: RabbitMQ остановлен на {started_at - stopped_at:.1f} с, оплат {len(placed)}, "
          f"медиана оплаты {statistics.median(pays):.1f} мс, все обработаны через {done_at - started_at:.1f} с "
          f"после запуска брокера, потеряно {lost}")


def write(label: str, rows: list[dict]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    columns = ["order_id", "pay_ms", "relay_ms", "kitchen_ms", "delivery_ms", "saga_ms"]
    with open(RESULTS / f"{label}.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: (f"{row[c]:.2f}" if isinstance(row.get(c), float) else row.get(c, "")) for c in columns})


def main() -> None:
    mode, base_url, label = sys.argv[1], sys.argv[2], sys.argv[3]
    headers = {"Authorization": f"Bearer {create_access_token(STUDENT_ID)}"}
    with httpx.Client(base_url=base_url, headers=headers, timeout=10) as client:
        {"latency": latency, "outage": outage}[mode](client, label)


if __name__ == "__main__":
    main()

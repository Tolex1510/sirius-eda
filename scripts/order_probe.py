"""
Время ответа POST /orders/create: последовательные заказы без параллельной нагрузки.
Токен студента берётся из файла, который печатает python -m app.cli load-users.

    python scripts/order_probe.py http://127.0.0.1:8000 tokens.txt before
"""
import csv
import statistics
import sys
import time
from pathlib import Path

import httpx

ORDERS = 30
RESULTS = Path("docs/lab5/results")

base_url, tokens_file, label = sys.argv[1], sys.argv[2], sys.argv[3]
token = Path(tokens_file).read_text().split()[0]
samples = []
with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30) as client:
    for _ in range(ORDERS):
        started = time.perf_counter()
        client.post("/orders/create", json={"item_id": 1, "quantity": 1}).raise_for_status()
        samples.append((time.perf_counter() - started) * 1000)

RESULTS.mkdir(parents=True, exist_ok=True)
with open(RESULTS / f"{label}_probe.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["request", "ms"])
    writer.writerows((number, f"{ms:.2f}") for number, ms in enumerate(samples, 1))

ordered = sorted(samples)
print(
    f"{label}: median={statistics.median(samples):.1f}ms "
    f"p95={ordered[int(len(ordered) * 0.95)]:.1f}ms max={ordered[-1]:.1f}ms"
)

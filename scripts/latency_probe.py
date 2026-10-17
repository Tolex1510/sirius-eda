"""
Время одного запроса без очереди: последовательные GET без параллельной нагрузки.
Locust при 500 пользователях меряет в основном ожидание в очереди, а здесь видно саму работу.

    python scripts/latency_probe.py http://127.0.0.1:8000 /menu/items
"""
import statistics
import sys
import time

import httpx

base_url, path = sys.argv[1], sys.argv[2]
with httpx.Client(base_url=base_url) as client:
    for _ in range(20):
        client.get(path)
    samples = []
    for _ in range(500):
        started = time.perf_counter()
        client.get(path).raise_for_status()
        samples.append((time.perf_counter() - started) * 1000)

samples.sort()
print(f"median={statistics.median(samples):.2f}ms p95={samples[int(len(samples) * 0.95)]:.2f}ms")

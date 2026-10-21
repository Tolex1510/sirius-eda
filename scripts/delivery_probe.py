"""
Цена выноса доставки в сервис: 500 последовательных GET /delivery/{id} через монолит
и столько же прямых вызовов GetDelivery по gRPC.

    python scripts/delivery_probe.py http  http://127.0.0.1:8000 <delivery_id> <user_id> grpc_http
    python scripts/delivery_probe.py grpc  localhost:50051       <delivery_id> <user_id> grpc_direct
"""
import csv
import statistics
import sys
import time
from pathlib import Path

import httpx

from app.core.jwt import create_access_token
from app.domain.entities import Role, User

REQUESTS = 500
WARM_UP = 20
RESULTS = Path("docs/lab6/results")

mode, target, delivery_id, user_id, label = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]

if mode == "http":
    client = httpx.Client(base_url=target, headers={"Authorization": f"Bearer {create_access_token(user_id)}"})

    def call():
        client.get(f"/delivery/{delivery_id}").raise_for_status()
else:
    from app.modules.delivery.grpc_client import GrpcDeliveryGateway, create_channel

    gateway = GrpcDeliveryGateway(create_channel(target), timeout=2)
    # Роль не важна: права проверяет сервис по данным из БД.
    actor = User(id=user_id, email="", phone=None, balance=0, is_blocked=False, role=Role.STUDENT)

    def call():
        gateway.get_delivery(delivery_id, actor)

for _ in range(WARM_UP):
    call()
samples = []
for _ in range(REQUESTS):
    started = time.perf_counter()
    call()
    samples.append((time.perf_counter() - started) * 1000)

RESULTS.mkdir(parents=True, exist_ok=True)
with open(RESULTS / f"{label}.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["request", "ms"])
    writer.writerows((number, f"{ms:.3f}") for number, ms in enumerate(samples, 1))

ordered = sorted(samples)
print(f"{label}: median={statistics.median(samples):.2f}ms p95={ordered[int(len(ordered) * 0.95)]:.2f}ms")

"""
Нагрузка «оформление заказов»: студенты заказывают блюда.
Токены студентов печатает python -m app.cli load-users, путь к файлу в LOCUST_TOKENS.

    LOCUST_TOKENS=tokens.txt locust -f locustfile_orders.py --host=http://127.0.0.1:8000
"""
import itertools
import os
import random
from pathlib import Path

from locust import HttpUser, between, task

TOKENS = itertools.cycle(Path(os.environ["LOCUST_TOKENS"]).read_text().split())
ITEM_IDS = range(1, 301)


class OrderUser(HttpUser):
    wait_time = between(2, 4)

    def on_start(self):
        self.client.headers["Authorization"] = f"Bearer {next(TOKENS)}"

    @task
    def create_order(self):
        self.client.post("/orders/create", json={"item_id": random.choice(ITEM_IDS), "quantity": 1})

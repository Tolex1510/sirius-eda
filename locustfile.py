"""
Нагрузка «обеденный перерыв»: студенты листают меню.
GET /menu/items и /menu/categories/{id} публичные, токен не нужен.

    locust -f locustfile.py --host=http://127.0.0.1:8000
"""
import random

from locust import HttpUser, between, task

CATEGORY_IDS = range(1, 13)


class MenuUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(4)
    def get_menu(self):
        self.client.get("/menu/items")

    @task(1)
    def get_category(self):
        self.client.get(f"/menu/categories/{random.choice(CATEGORY_IDS)}", name="/menu/categories/[id]")

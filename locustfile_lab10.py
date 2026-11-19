"""Mixed 70/20/10 traffic against a disposable fixture, never hard-coded menu IDs.

LOCUST_TOKENS=/private/tokens.txt locust -f locustfile_lab10.py --host=http://127.0.0.1:8000
Run scripts/lab10_load.py to provision a safe disposable target automatically.
"""
import itertools
import os
import random
from pathlib import Path
from locust import HttpUser, between, task

_tokens = None


class SiriusUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        global _tokens
        if _tokens is None:
            path = os.getenv('LOCUST_TOKENS')
            if not path:
                raise RuntimeError('Set LOCUST_TOKENS to a private fixture token file')
            tokens = Path(path).read_text().split()
            if not tokens:
                raise RuntimeError('Fixture token file is empty')
            _tokens = itertools.cycle(tokens)
        self.client.headers['Authorization'] = 'Bearer ' + next(_tokens)
        response = self.client.get('/menu/items', name='/menu/items [setup]')
        response.raise_for_status()
        self.items = [row['id'] for row in response.json() if row['is_available']]
        if not self.items:
            raise RuntimeError('Target has no available menu fixtures')

    @task(7)
    def menu(self):
        self.client.get('/menu/items')

    @task(2)
    def detail(self):
        self.client.get(f'/menu/items/{random.choice(self.items)}', name='/menu/items/[id]')

    @task(1)
    def order(self):
        with self.client.post('/orders/create', json={'item_id': random.choice(self.items), 'quantity': 1},
                              catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f'Create returned {response.status_code}')
            elif not response.json().get('order_id'):
                response.failure('Missing persisted order ID')

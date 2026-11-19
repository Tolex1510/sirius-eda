"""Конкурентные HTTP-проверки на автономном demo-шлюзе, без настоящих денег.

python scripts/payment_probe.py --host http://localhost:8080 --count 100 --create-test-user
Создаёт временного пользователя и неоплаченные заказы; используйте учебный стенд.
Пароль и токен никогда не печатаются. Результат — JSON с задержками и числами дублей.
"""
import argparse
import asyncio
import json
import math
import secrets
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
import httpx


async def main(args):
    async with httpx.AsyncClient(base_url=args.host.rstrip('/') + '/api/', timeout=90,
                                 limits=httpx.Limits(max_connections=args.count, max_keepalive_connections=args.count)) as client:
        config = (await client.get('payments/config')).json()
        if config['provider'] != 'demo':
            raise SystemExit('Эта проверка разрешена только для demo-шлюза')
        email, password = f'probe-{secrets.token_hex(6)}@example.ru', secrets.token_urlsafe(16)
        registered = await client.post('users/register', json={'email': email, 'password': password})
        registered.raise_for_status()
        login = await client.post('auth/login', json={'email': email, 'password': password})
        login.raise_for_status()
        client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
        items = (await client.get('menu/items')).json()
        item = next(i for i in items if i['is_available'])

        async def order():
            response = await client.post('payments/checkout', json={'item_id': item['id'], 'quantity': 1})
            response.raise_for_status()
            return response.json()['id']

        async def pay(order_id, key):
            started = time.perf_counter()
            response = await client.post('payments', json={'order_id': order_id, 'amount': str(item['price'])}, headers={'Idempotency-Key': key})
            return response.status_code, response.json().get('id'), (time.perf_counter() - started) * 1000

        def summary(rows):
            values = sorted(r[2] for r in rows)
            return {'requests': len(rows), 'successful': sum(r[0] == 200 for r in rows),
                    'distinct_payment_ids': len({r[1] for r in rows if r[1]}),
                    'median_ms': round(statistics.median(values), 2),
                    'p95_ms': round(values[math.ceil(len(values) * .95) - 1], 2),
                    'statuses': {str(code): sum(r[0] == code for r in rows) for code in {r[0] for r in rows}}}

        one_order = await order()
        duplicates = await asyncio.gather(*(pay(one_order, 'duplicate-payment-key') for _ in range(args.count)))
        many_orders = [await order() for _ in range(args.count)]
        independent = await asyncio.gather(*(pay(order_id, f'probe-order-{order_id}') for order_id in many_orders))
        report = {'at': datetime.now(UTC).isoformat(), 'host': args.host, 'provider': 'demo',
                  'note': 'Локальный HTTP/БД стенд. Это не замер производительности ЮKassa.',
                  'duplicates': summary(duplicates), 'independent': summary(independent)}
        # Отмена не создаёт платежей и возвращает созданные нами заказы в закрытое состояние.
        for order_id in [one_order, *many_orders]:
            response = await client.post(f'payments/orders/{order_id}/cancel')
            response.raise_for_status()
        payments = (await client.get('payments')).json()
        for payment in payments:
            response = await client.post(f"payments/{payment['id']}/demo", json={'status': 'canceled'})
            response.raise_for_status()
        assert len([p for p in payments if p['order_id'] == one_order]) == 1
        assert report['duplicates']['distinct_payment_ids'] == 1
        assert report['duplicates']['successful'] == args.count
        assert report['independent']['distinct_payment_ids'] == args.count
        assert report['independent']['successful'] == args.count
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='http://localhost:8080')
    parser.add_argument('--count', type=int, default=100, choices=range(1, 501))
    parser.add_argument('--create-test-user', action='store_true', required=True)
    parser.add_argument('--output', type=Path, default=Path('docs/study/results/payment_probe.json'))
    asyncio.run(main(parser.parse_args()))

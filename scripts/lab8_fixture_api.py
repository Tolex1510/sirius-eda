"""Изолированный FastAPI для проверки SSR/CSR. Только localhost, данные в памяти.

Не использует БД, реальные платежи или учётные записи проекта.
Запуск: .venv/bin/python scripts/lab8_fixture_api.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(REPOSITORY_BACKEND='memory', DATABASE_URL='postgresql://unused:unused@localhost:1/unused',
                  SECRET_KEY='lab8-isolated-local-verification-secret', PAYMENT_PROVIDER='demo',
                  YOOKASSA_SHOP_ID='', YOOKASSA_SECRET_KEY='', BCRYPT_ROUNDS='4', MENU_CACHE_ENABLED='false')

import asyncio
import uvicorn
from app.main import app
from app.dependencies import memory_storage
from app.core.security import hash_password
from app.domain.entities import Role, User
from app.modules.menu.service import MenuService
from app.modules.menu.repository import InMemoryMenuRepository
from deploy.seed import MENU

service = MenuService(InMemoryMenuRepository(memory_storage))
for name, items in MENU.items():
    category = service.create_category(name)
    for title, price in items:
        service.create_item(title, price, category.id)
uid = memory_storage.next_id('users')
memory_storage.users[uid] = User(id=uid, email='lab8@example.ru', phone=None, role=Role.ADMIN,
                                password_hash=hash_password('lab8-local-fixture'), balance=0, is_blocked=False)

@app.middleware('http')
async def delay_fixture_menu(request, call_next):
    if request.url.path.startswith('/menu/'):
        await asyncio.sleep(float(os.environ.get('LAB8_DELAY_SECONDS', '0')))
    return await call_next(request)

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('LAB8_API_PORT', '8092')))

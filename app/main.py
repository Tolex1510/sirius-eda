"""
Точка входа приложения. Инициализирует FastAPI и подключает модули.
Схему БД создаёт и меняет Alembic: alembic upgrade head.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.dependencies import warm_up_menu_cache
from app.modules.delivery.grpc_client import close_delivery_channel
from app.modules.auth.router import router as auth_router
from app.modules.delivery.router import router as delivery_router
from app.modules.kitchen.router import router as kitchen_queue_router
from app.modules.menu.router import router as menu_router
from app.modules.orders.router import kitchen_router
from app.modules.orders.router import router as orders_router
from app.modules.users.router import router as users_router



@asynccontextmanager
async def lifespan(_: FastAPI):
    # Прогрев кеша: первые запросы после старта сразу попадают в Redis, а не в PostgreSQL.
    await run_in_threadpool(warm_up_menu_cache)
    yield
    close_delivery_channel()


# Swagger раскрывает структуру API, поэтому в продакшене (DEBUG=false) он выключен.
app = FastAPI(
    title="Sirius.Food API",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(users_router, prefix="/users", tags=["users"])
app.include_router(menu_router, prefix="/menu", tags=["menu"])
app.include_router(orders_router, prefix="/orders", tags=["orders"])
app.include_router(kitchen_router, prefix="/kitchen", tags=["kitchen"])
app.include_router(kitchen_queue_router, prefix="/kitchen", tags=["kitchen"])
app.include_router(delivery_router, prefix="/delivery", tags=["delivery"])

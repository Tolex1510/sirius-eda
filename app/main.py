"""
Точка входа приложения. Инициализирует FastAPI и подключает модули.
Схему БД создаёт и меняет Alembic: alembic upgrade head.
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from app.core.config import settings
from app.dependencies import warm_up_menu_cache
from app.modules.delivery.grpc_client import close_delivery_channel
from app.modules.auth.router import router as auth_router
from app.modules.delivery.router import router as delivery_router
from app.modules.kitchen.router import router as kitchen_queue_router
from app.modules.menu.router import router as menu_router
from app.modules.orders.router import kitchen_router
from app.modules.orders.router import router as orders_router
from app.modules.auth.session_router import router as session_router
from app.modules.assistant.router import router as assistant_router
from app.modules.payments.router import router as payments_router
from app.modules.users.router import router as users_router
from app.core.observability import configure_app
from app.core.dependencies import require_role
from app.domain.entities import Role



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
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(users_router, prefix="/users", tags=["users"])
app.include_router(menu_router, prefix="/menu", tags=["menu"])
app.include_router(orders_router, prefix="/orders", tags=["orders"])
app.include_router(kitchen_router, prefix="/kitchen", tags=["kitchen"])
app.include_router(kitchen_queue_router, prefix="/kitchen", tags=["kitchen"])
app.include_router(delivery_router, prefix="/delivery", tags=["delivery"])

app.include_router(payments_router, prefix="/payments", tags=["payments"])

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}

app.include_router(session_router, prefix="/auth/session", tags=["session"])
app.include_router(assistant_router, prefix="/assistant", tags=["assistant"])

configure_app(app)
Instrumentator(
    excluded_handlers=["/metrics", "/health"],
    should_group_status_codes=False,
).add(metrics.default(
    # Default per-handler buckets stop at 1 s and hide slow requests in +Inf.
    latency_lowr_buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 7.5, 10, 20, 30, 60, 180),
)).instrument(app).expose(app, include_in_schema=False)

if settings.DEBUG:
    @app.get("/debug/observability/error", include_in_schema=False)
    def observability_demo_error(_: object = Depends(require_role(Role.ADMIN))):
        raise RuntimeError("Sirius observability demo error")

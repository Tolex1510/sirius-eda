"""
Запуск микросервиса доставки.

    python -m delivery_service
"""
import structlog
import signal
from collections.abc import Iterator
from concurrent import futures
from contextlib import contextmanager

import grpc

import delivery_pb2_grpc
from app.core.config import settings
from app.core.observability import configure_worker
from app.database import SessionLocal
from app.modules.delivery.repository import DeliveryRepository, SqlAlchemyDeliveryRepository
from delivery_service.servicer import DeliveryServicer

logger = structlog.get_logger("delivery_service")

# Стрим занимает поток на всё время подписки, поэтому потоков больше, чем ядер.
MAX_WORKERS = 32
SHUTDOWN_GRACE_SECONDS = 5


@contextmanager
def sql_repository() -> Iterator[DeliveryRepository]:
    # Общая с монолитом БД, как в методичке. Своя БД сервиса описана в README.
    db = SessionLocal()
    try:
        yield SqlAlchemyDeliveryRepository(db)
    finally:
        db.close()


def build_server(servicer: DeliveryServicer, address: str) -> tuple[grpc.Server, int]:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    delivery_pb2_grpc.add_DeliveryServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port(address)
    return server, port


def serve() -> None:
    configure_worker("sirius-delivery-grpc")
    server, _ = build_server(DeliveryServicer(sql_repository), settings.DELIVERY_GRPC_BIND)
    server.start()
    logger.info("delivery_grpc_started", address=settings.DELIVERY_GRPC_BIND)
    # SIGTERM от systemd или Docker: новые вызовы отклоняются, начатые получают время закончить.
    signal.signal(signal.SIGTERM, lambda *_: server.stop(SHUTDOWN_GRACE_SECONDS))
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(SHUTDOWN_GRACE_SECONDS).wait()
    logger.info("delivery_grpc_stopped")

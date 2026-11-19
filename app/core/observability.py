"""Общая настройка JSON-логов, correlation ID, Prometheus, Sentry и OpenTelemetry."""
import logging
import os
import re
import sys
import time
import uuid
from threading import Lock

import structlog
from structlog import get_logger
from fastapi import FastAPI, Request
from prometheus_client import Counter
from celery.signals import setup_logging as celery_setup_logging

from app.core.config import settings

_setup_lock = Lock()
_logging_ready = False
_tracing_ready = False
_correlation_pattern = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

cache_operations = Counter(
    "sirius_cache_operations_total",
    "Результат операций чтения кеша меню",
    ("result",),
)
orders_created = Counter(
    "sirius_orders_created_total",
    "Количество успешно созданных заказов",
)


def _add_trace_context(_logger, _method, event_dict):
    try:
        from opentelemetry import trace

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            event_dict["trace_id"] = f"{span_context.trace_id:032x}"
            event_dict["span_id"] = f"{span_context.span_id:016x}"
    except ImportError:
        pass
    return event_dict


def setup_logging() -> None:
    """Направляет structlog и стандартный logging в stdout как однострочный JSON."""
    global _logging_ready
    if _logging_ready:
        return
    with _setup_lock:
        if _logging_ready:
            return
        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _add_trace_context,
        ]
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(),
                foreign_pre_chain=shared_processors,
            )
        )
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(logging.INFO)
        structlog.configure(
            processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.task", "celery.redirected"):
            logging.getLogger(name).handlers = [handler]
            logging.getLogger(name).propagate = False
        _logging_ready = True


def init_tracing(service_name: str) -> bool:
    """Включает OTel при наличии OTLP endpoint; локальный запуск без Jaeger остаётся рабочим."""
    global _tracing_ready
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        return False
    if _tracing_ready:
        return True
    with _setup_lock:
        if _tracing_ready:
            return True
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=endpoint.startswith("http://")))
        )
        trace.set_tracer_provider(provider)
        _tracing_ready = True
    return True


def instrument_database() -> None:
    if not _tracing_ready:
        return
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    from app.database import engine

    SQLAlchemyInstrumentor().instrument(engine=engine)


def configure_app(app: FastAPI, service_name: str = "sirius-api") -> None:
    setup_logging()
    tracing_enabled = init_tracing(service_name)
    logger = get_logger(service_name)
    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[FastApiIntegration()],
            send_default_pii=False,
            traces_sample_rate=0.0,
        )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        supplied = request.headers.get("X-Correlation-ID", "")
        correlation_id = supplied if _correlation_pattern.fullmatch(supplied) else uuid.uuid4().hex
        started = time.perf_counter()
        request.state.correlation_id = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        try:
            if settings.SENTRY_DSN:
                import sentry_sdk

                # SDK уже создал isolation scope для запроса. Вложенная область
                # закрылась бы до перехвата исключения внешним middleware Sentry.
                sentry_sdk.set_tag("correlation_id", correlation_id)
                response = await call_next(request)
            else:
                response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            logger.info(
                "http_request_completed", method=request.method, path=request.url.path,
                status_code=response.status_code, duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return response
        except Exception:
            logger.exception(
                "http_request_failed", method=request.method, path=request.url.path,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()

    if tracing_enabled:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        instrument_database()


def correlation_id_from_context() -> str | None:
    return structlog.contextvars.get_contextvars().get("correlation_id")


def current_traceparent() -> str | None:
    try:
        from opentelemetry.propagate import inject

        carrier: dict[str, str] = {}
        inject(carrier)
        return carrier.get("traceparent")
    except ImportError:
        return None


def start_span(name: str):
    from opentelemetry import trace

    return trace.get_tracer("sirius.eda").start_as_current_span(name)


def configure_worker(service_name: str) -> None:
    setup_logging()
    if init_tracing(service_name):
        instrument_database()


@celery_setup_logging.connect
def _configure_celery_logging(**_kwargs) -> None:
    setup_logging()

"""
Приложение Celery. Брокер и хранилище результатов в Redis.

    celery -A app.core.celery_app worker --loglevel=info
    celery -A app.core.celery_app beat --loglevel=info
    celery -A app.core.celery_app flower --address=127.0.0.1 --port=5555
"""
from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

from app.core.config import settings

celery_app = Celery(
    "sirius_food",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.orders", "app.tasks.maintenance"],
)

DEFAULT_QUEUE = Queue("default", Exchange("default"), routing_key="default")
# Очереди мёртвых писем нет в task_queues, поэтому воркер её не слушает.
# Иначе упавшая задача сразу запускалась бы снова и ходила по кругу.
DEAD_LETTER_QUEUE = Queue("dlq", Exchange("dlq"), routing_key="dlq")

celery_app.conf.update(
    # JSON вместо pickle: из брокера нельзя прислать исполняемый объект.
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_queues=(DEFAULT_QUEUE,),
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    # Подтверждение после выполнения: если воркер умер посреди задачи, брокер выдаст её снова.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Через сколько Redis вернёт в очередь неподтверждённую задачу. Должно быть больше
    # времени выполнения и задержки ретраев, иначе задача выполнится дважды.
    broker_transport_options={"visibility_timeout": 300},
    task_time_limit=60,
    # Результаты задач никто не ждёт: итог пишется в task_logs, Flower берёт его из событий.
    # Без этого .delay() подписывается на результат в Redis и при его падении висит на переподключениях.
    task_ignore_result=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    # Без брокера заказ всё равно должен ответить быстро, а не висеть на переподключениях.
    task_publish_retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.2},
    # События для Flower: задачи видны в реальном времени, включая момент постановки в очередь.
    worker_send_task_events=True,
    task_send_sent_event=True,
    beat_schedule={
        "refresh-order-stats": {
            "task": "app.tasks.maintenance.refresh_order_stats",
            "schedule": 60.0,
        },
        "requeue-lost-order-tasks": {
            "task": "app.tasks.maintenance.requeue_lost_order_tasks",
            "schedule": 60.0,
        },
        "cleanup-task-logs": {
            "task": "app.tasks.maintenance.cleanup_task_logs",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)

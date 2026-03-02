import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

celery_app = Celery(
    "travelman",
    broker=REDIS_URL,
    backend=REDIS_URL,
)
celery_app.conf.update(task_serializer="json", result_serializer="json")

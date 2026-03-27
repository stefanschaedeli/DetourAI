import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

celery_app = Celery(
    "detour-ai",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.run_planning_job",
        "tasks.prefetch_accommodations",
        "tasks.remove_stop_job",
        "tasks.add_stop_job",
        "tasks.reorder_stops_job",
        "tasks.replace_stop_job",
    ],
)
celery_app.conf.update(task_serializer="json", result_serializer="json")

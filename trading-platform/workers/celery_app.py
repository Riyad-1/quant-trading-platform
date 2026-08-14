"""Celery application for background tasks."""

from celery import Celery
import os

# Get configuration from environment
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "quant_trading",
    broker=redis_url,
    backend=redis_url,
    include=[
        "workers.tasks_data",
        "workers.tasks_features",
        "workers.tasks_ml",
    ]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    worker_prefetch_multiplier=1,
)
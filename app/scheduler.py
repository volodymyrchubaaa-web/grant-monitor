from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db import SessionLocal
from app.pipeline.run import run_pipeline

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def _scheduled_run() -> None:
    db = SessionLocal()
    try:
        stats = run_pipeline(db)
        logger.info("Scheduled fetch pipeline finished: %s", stats)
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        _scheduled_run,
        "interval",
        hours=settings.fetch_interval_hours,
        id="fetch_grants",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

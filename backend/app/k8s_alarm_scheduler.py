import asyncio
import logging

from app.config import settings
from app.database import SessionLocal
from app.k8s_alarm_evaluator_service import evaluate_k8s_alarms_async

logger = logging.getLogger(__name__)


async def k8s_alarm_scheduler() -> None:
    interval = max(60, settings.k8s_alarm_monitor_interval_seconds)
    logger.info("K8s alarm scheduler started, interval=%ss", interval)
    while True:
        try:
            db = SessionLocal()
            try:
                await evaluate_k8s_alarms_async(db)
            finally:
                db.close()
        except Exception:
            logger.exception("K8s alarm scheduler iteration failed")
        await asyncio.sleep(interval)

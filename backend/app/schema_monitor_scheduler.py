import asyncio
import logging

from app.config import settings
from app.database import SessionLocal
from app.schema_monitor_service import list_schema_monitor_targets, scan_subscription_schema_async

logger = logging.getLogger(__name__)


async def schema_monitor_scheduler() -> None:
    interval = max(60, settings.schema_monitor_interval_seconds)
    logger.info("Schema monitor scheduler started, interval=%ss", interval)
    while True:
        try:
            db = SessionLocal()
            try:
                targets = list_schema_monitor_targets(db)
                if not targets:
                    logger.debug("Schema monitor: no enabled targets")
                for sub in targets:
                    try:
                        result = await scan_subscription_schema_async(db, sub)
                        if result["changes_detected"]:
                            logger.info(
                                "Schema monitor: subscription=%s changes=%s logs=%s",
                                sub.id,
                                result["changes_detected"],
                                result["logs_created"],
                            )
                    except Exception:
                        logger.exception("Schema monitor scan failed for subscription %s", sub.id)
            finally:
                db.close()
        except Exception:
            logger.exception("Schema monitor scheduler iteration failed")
        await asyncio.sleep(interval)

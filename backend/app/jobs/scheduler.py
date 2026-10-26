import asyncio

import structlog

from app.core.database import SessionLocal
from app.services.sla import run_sla_check

log = structlog.get_logger()


async def sla_scheduler(stop: asyncio.Event):
    """Hourly in-process scheduler; production deployments may call the same idempotent job externally."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=3600)
            continue
        except TimeoutError:
            pass
        try:
            db = SessionLocal()
            try:
                result = run_sla_check(db)
                log.info("scheduled_sla_check", **result)
            finally:
                db.close()
        except Exception as exc:
            log.error("scheduled_sla_check_failed", error=str(exc)[:300])



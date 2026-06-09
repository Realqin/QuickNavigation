import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm.attributes import flag_modified

from app.database import SessionLocal
from app.models import Connection
from app.ping_service import check_url_reachable

logger = logging.getLogger(__name__)

PING_INTERVAL_SECONDS = 180


async def ping_connection_url(url: str) -> bool:
    return await check_url_reachable(url)


def _update_sub_link_status(sub_links: list, index: int, reachable: bool, checked_at: datetime) -> list:
    updated = [dict(item) for item in sub_links]
    updated[index]["is_reachable"] = reachable
    updated[index]["last_checked_at"] = checked_at.isoformat()
    return updated


async def ping_connection_record(
    connection_id: int,
    sub_index: int | None = None,
) -> Connection | None:
    db = SessionLocal()
    try:
        connection = db.query(Connection).filter(Connection.id == connection_id).first()
        if not connection:
            return None

        now = datetime.utcnow()

        if sub_index is not None:
            sub_links = connection.sub_links or []
            if sub_index < 0 or sub_index >= len(sub_links):
                return None
            reachable = await ping_connection_url(sub_links[sub_index]["url"])
            connection.sub_links = _update_sub_link_status(sub_links, sub_index, reachable, now)
            flag_modified(connection, "sub_links")
        else:
            reachable = await ping_connection_url(connection.url)
            connection.is_reachable = reachable
            connection.last_checked_at = now

        db.commit()
        db.refresh(connection)
        return connection
    finally:
        db.close()


async def _ping_connection_with_subs(connection: Connection) -> None:
    now = datetime.utcnow()
    main_result = await ping_connection_url(connection.url)
    connection.is_reachable = bool(main_result)
    connection.last_checked_at = now

    sub_links = connection.sub_links or []
    if not sub_links:
        return

    results = await asyncio.gather(
        *(ping_connection_url(item["url"]) for item in sub_links),
        return_exceptions=True,
    )
    updated: list[dict] = []
    for item, result in zip(sub_links, results, strict=True):
        row = dict(item)
        if isinstance(result, Exception):
            row["is_reachable"] = False
        else:
            row["is_reachable"] = bool(result)
        row["last_checked_at"] = now.isoformat()
        updated.append(row)
    connection.sub_links = updated
    flag_modified(connection, "sub_links")


async def ping_all_connections() -> int:
    db = SessionLocal()
    try:
        connections = db.query(Connection).all()
        if not connections:
            return 0

        await asyncio.gather(*(_ping_connection_with_subs(conn) for conn in connections))
        db.commit()
        return len(connections)
    finally:
        db.close()


async def connection_ping_scheduler() -> None:
    while True:
        try:
            count = await ping_all_connections()
            logger.info("Scheduled ping completed for %s connections", count)
        except Exception:
            logger.exception("Scheduled ping failed")
        await asyncio.sleep(PING_INTERVAL_SECONDS)

import asyncio
import logging
from datetime import datetime

import httpx
from sqlalchemy.orm.attributes import flag_modified

from app.database import SessionLocal
from app.models import Connection
from app.ping_service import PING_CONCURRENCY, PING_TIMEOUT, ping_urls_with_client

logger = logging.getLogger(__name__)

PING_INTERVAL_SECONDS = 900


def _update_sub_link_status(sub_links: list, index: int, reachable: bool, checked_at: datetime) -> list:
    updated = [dict(item) for item in sub_links]
    updated[index]["is_reachable"] = reachable
    updated[index]["last_checked_at"] = checked_at.isoformat()
    return updated


async def ping_connection_record(
    connection_id: int,
    sub_index: int | None = None,
) -> Connection | None:
    from app.ping_service import check_url_reachable

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
            reachable = await check_url_reachable(sub_links[sub_index]["url"])
            connection.sub_links = _update_sub_link_status(sub_links, sub_index, reachable, now)
            flag_modified(connection, "sub_links")
        else:
            reachable = await check_url_reachable(connection.url)
            connection.is_reachable = reachable
            connection.last_checked_at = now

        db.commit()
        db.refresh(connection)
        return connection
    finally:
        db.close()


def _apply_ping_results(connection: Connection, results: dict[str, bool], checked_at: datetime) -> None:
    main_url = (connection.url or "").strip()
    connection.is_reachable = bool(results.get(main_url, False))
    connection.last_checked_at = checked_at

    sub_links = connection.sub_links or []
    if not sub_links:
        return

    updated: list[dict] = []
    for item in sub_links:
        row = dict(item)
        url = str(row.get("url") or "").strip()
        row["is_reachable"] = bool(results.get(url, False))
        row["last_checked_at"] = checked_at.isoformat()
        updated.append(row)
    connection.sub_links = updated
    flag_modified(connection, "sub_links")


async def ping_all_connections(*, client: httpx.AsyncClient) -> int:
    db = SessionLocal()
    try:
        connections = db.query(Connection).all()
        if not connections:
            return 0

        urls: list[str] = []
        for connection in connections:
            main_url = (connection.url or "").strip()
            if main_url:
                urls.append(main_url)
            for item in connection.sub_links or []:
                sub_url = str(item.get("url") or "").strip()
                if sub_url:
                    urls.append(sub_url)

        reachability = (
            dict(zip(urls, await ping_urls_with_client(urls, client=client), strict=False))
            if urls
            else {}
        )
        checked_at = datetime.utcnow()
        for connection in connections:
            _apply_ping_results(connection, reachability, checked_at)

        db.commit()
        return len(connections)
    finally:
        db.close()


async def connection_ping_scheduler() -> None:
    limits = httpx.Limits(max_connections=PING_CONCURRENCY, max_keepalive_connections=PING_CONCURRENCY)
    async with httpx.AsyncClient(
        timeout=PING_TIMEOUT,
        follow_redirects=True,
        verify=False,
        limits=limits,
    ) as client:
        while True:
            try:
                count = await ping_all_connections(client=client)
                logger.info("Scheduled ping completed for %s connections", count)
            except Exception:
                logger.exception("Scheduled ping failed")
            await asyncio.sleep(PING_INTERVAL_SECONDS)

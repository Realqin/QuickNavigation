import logging
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from app.config import settings
from app.models import Connection

logger = logging.getLogger(__name__)

LOCAL_HOST_ALIASES = {"localhost", "127.0.0.1", "0.0.0.0"}


def resolve_redis_host(host: str | None) -> str:
    normalized = (host or "").strip().lower()
    if normalized in LOCAL_HOST_ALIASES:
        return settings.redisinsight_redis_host
    return (host or "").strip()


def build_redisinsight_public_base(request_host: str | None = None) -> str:
    if request_host:
        hostname = request_host.split(":")[0].strip()
        if hostname:
            return f"http://{hostname}:{settings.redisinsight_public_port}"
    configured = settings.public_webhook_base_url.strip()
    if configured:
        parsed = urlparse(configured)
        if parsed.hostname and parsed.hostname not in LOCAL_HOST_ALIASES:
            scheme = parsed.scheme or "http"
            return f"{scheme}://{parsed.hostname}:{settings.redisinsight_public_port}"
    return f"http://localhost:{settings.redisinsight_public_port}"


def _database_payload(conn: Connection, *, name: str | None = None) -> dict:
    host = resolve_redis_host(conn.host)
    if not host:
        raise HTTPException(status_code=400, detail="Redis 连接未配置主机")
    payload: dict = {
        "name": name or conn.name,
        "host": host,
        "port": int(conn.port or 6379),
    }
    password = (conn.password or "").strip()
    if password:
        payload["password"] = password
    username = (conn.username or "").strip()
    if username:
        payload["username"] = username
    return payload


def _ensure_eula_accepted(client: httpx.Client) -> None:
    response = client.get("/api/settings")
    response.raise_for_status()
    agreements = (response.json() or {}).get("agreements") or {}
    if agreements.get("eula"):
        return
    patch_response = client.patch(
        "/api/settings",
        json={
            "agreements": {
                "eula": True,
                "analytics": False,
                "notifications": False,
                "encryption": False,
            }
        },
    )
    patch_response.raise_for_status()


def _find_database_id_by_name(client: httpx.Client, name: str) -> str | None:
    response = client.get("/api/databases")
    response.raise_for_status()
    for item in response.json() or []:
        if item.get("name") == name:
            return str(item.get("id") or "") or None
    return None


def _raise_redisinsight_error(response: httpx.Response, *, action: str) -> None:
    detail = response.text.strip()
    try:
        body = response.json()
        detail = str(body.get("message") or body.get("detail") or detail)
    except ValueError:
        pass
    raise HTTPException(
        status_code=502,
        detail=f"RedisInsight {action}失败：{detail}",
    )


def sync_connection_to_redisinsight(conn: Connection, *, external_name: str | None = None) -> str:
    display_name = external_name or conn.name
    payload = _database_payload(conn, name=display_name)
    base_url = settings.redisinsight_internal_url.rstrip("/")
    if not base_url:
        raise HTTPException(status_code=503, detail="RedisInsight 未配置")

    with httpx.Client(base_url=base_url, timeout=30) as client:
        _ensure_eula_accepted(client)
        database_id = _find_database_id_by_name(client, display_name)
        if database_id:
            response = client.patch(f"/api/databases/{database_id}", json=payload)
            if response.status_code >= 400:
                _raise_redisinsight_error(response, action="更新连接")
            database_id = str((response.json() or {}).get("id") or database_id)
        else:
            response = client.post("/api/databases", json=payload)
            if response.status_code >= 400:
                _raise_redisinsight_error(response, action="创建连接")
            database_id = str((response.json() or {}).get("id") or "")
        if not database_id:
            raise HTTPException(status_code=502, detail="RedisInsight 未能创建连接")
        return database_id


def delete_redisinsight_database(database_id: str) -> None:
    if not database_id:
        return
    base_url = settings.redisinsight_internal_url.rstrip("/")
    if not base_url:
        return
    with httpx.Client(base_url=base_url, timeout=30) as client:
        response = client.delete(f"/api/databases/{database_id}")
        if response.status_code >= 400:
            _raise_redisinsight_error(response, action="删除连接")


def prepare_redisinsight_open(
    conn: Connection,
    *,
    public_base: str,
    external_name: str | None = None,
) -> dict:
    database_id = sync_connection_to_redisinsight(conn, external_name=external_name)
    return {
        "embed_url": f"{public_base.rstrip('/')}/{database_id}/browser",
        "connection_name": conn.name,
        "database_id": database_id,
    }

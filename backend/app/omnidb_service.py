import json
import logging
import os
import sqlite3
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import HTTPException

from app.config import settings
from app.models import Connection

logger = logging.getLogger(__name__)

LOCAL_HOST_ALIASES = {"localhost", "127.0.0.1", "0.0.0.0"}


def resolve_database_host(host: str | None) -> str:
    normalized = (host or "").strip().lower()
    if normalized in LOCAL_HOST_ALIASES:
        return settings.omnidb_mysql_host
    return (host or "").strip()


def build_omnidb_public_base(request_host: str | None = None) -> str:
    if request_host:
        hostname = request_host.split(":")[0].strip()
        if hostname:
            return f"http://{hostname}:{settings.omnidb_public_port}"
    configured = settings.public_webhook_base_url.strip()
    if configured:
        parsed = urlparse(configured)
        if parsed.hostname and parsed.hostname not in LOCAL_HOST_ALIASES:
            scheme = parsed.scheme or "http"
            return f"{scheme}://{parsed.hostname}:{settings.omnidb_public_port}"
    return f"http://localhost:{settings.omnidb_public_port}"


def build_omnidb_login_url(*, public_base: str) -> str:
    params = urlencode(
        {
            "user": settings.omnidb_admin_user,
            "pwd": settings.omnidb_admin_password,
        }
    )
    return f"{public_base.rstrip('/')}/omnidb_login/?{params}"


def _connection_payload(
    conn: Connection,
    *,
    omnidb_id: int = -1,
    alias: str | None = None,
) -> dict:
    return {
        "id": omnidb_id,
        "type": "mysql",
        "title": alias or conn.name,
        "server": resolve_database_host(conn.host),
        "port": str(conn.port or 3306),
        "database": conn.database_name or "",
        "user": conn.username or "",
        "password": conn.password or "",
        "connstring": "",
        "public": False,
        "tunnel": {
            "enabled": False,
            "server": "",
            "port": "",
            "user": "",
            "password": "",
            "key": "",
        },
    }


def _extract_csrf_token(client: httpx.Client) -> str:
    return client.cookies.get("omnidb_csrftoken", "") or client.cookies.get("csrftoken", "")


def _login_omnidb(client: httpx.Client) -> None:
    response = client.get(
        "/omnidb_login/",
        params={
            "user": settings.omnidb_admin_user,
            "pwd": settings.omnidb_admin_password,
        },
    )
    response.raise_for_status()
    client.get("/").raise_for_status()


def _find_connection_id_by_alias(client: httpx.Client, alias: str) -> int:
    csrf = _extract_csrf_token(client)
    response = client.post(
        "/get_connections/",
        data={"data": json.dumps({"p_conn_id_list": []})},
        headers={"X-CSRFToken": csrf, "Referer": settings.omnidb_internal_url},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("v_error"):
        raise HTTPException(status_code=502, detail=f"OmniDB 查询连接失败：{payload.get('v_data')}")

    for item in (payload.get("v_data") or {}).get("v_conn_list", []):
        if item.get("alias") == alias and item.get("technology") == "mysql":
            return int(item["id"])
    return -1


def _save_connection_via_api(
    client: httpx.Client,
    conn: Connection,
    omnidb_id: int,
    *,
    alias: str,
) -> int:
    payload = _connection_payload(conn, omnidb_id=omnidb_id, alias=alias)
    csrf = _extract_csrf_token(client)
    response = client.post(
        "/save_connection/",
        data={"data": json.dumps(payload)},
        headers={"X-CSRFToken": csrf, "Referer": settings.omnidb_internal_url},
    )
    response.raise_for_status()
    body = response.json()
    if body.get("v_error"):
        raise HTTPException(status_code=502, detail=f"OmniDB 保存连接失败：{body.get('v_data')}")
    return _find_connection_id_by_alias(client, alias)


def _omnidb_db_path() -> str | None:
    configured = settings.omnidb_db_path.strip()
    if configured and os.path.isfile(configured):
        return configured
    return None


def clear_omnidb_workspace_tabs() -> None:
    db_path = _omnidb_db_path()
    if not db_path:
        return

    try:
        with sqlite3.connect(db_path) as sqlite_conn:
            user_row = sqlite_conn.execute(
                "SELECT id FROM auth_user WHERE username = ? LIMIT 1",
                (settings.omnidb_admin_user,),
            ).fetchone()
            if not user_row:
                logger.warning("omnidb admin user not found in sqlite db")
                return
            user_id = int(user_row[0])
            sqlite_conn.execute(
                "DELETE FROM OmniDB_app_tab WHERE user_id = ?",
                (user_id,),
            )
            sqlite_conn.commit()
    except sqlite3.Error as exc:
        logger.warning("clear omnidb workspace tabs failed: %s", exc)


def prepare_omnidb_menu_url(*, public_base: str) -> str:
    clear_omnidb_workspace_tabs()
    return build_omnidb_login_url(public_base=public_base)


def _ensure_workspace_tab(omnidb_conn_id: int, tab_title: str) -> None:
    db_path = _omnidb_db_path()
    if not db_path or omnidb_conn_id <= 0:
        return

    try:
        with sqlite3.connect(db_path) as sqlite_conn:
            user_row = sqlite_conn.execute(
                "SELECT id FROM auth_user WHERE username = ? LIMIT 1",
                (settings.omnidb_admin_user,),
            ).fetchone()
            if not user_row:
                logger.warning("omnidb admin user not found in sqlite db")
                return
            user_id = int(user_row[0])

            sqlite_conn.execute(
                "DELETE FROM OmniDB_app_tab WHERE user_id = ?",
                (user_id,),
            )
            sqlite_conn.execute(
                """
                INSERT INTO OmniDB_app_tab (user_id, connection_id, title, snippet)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, omnidb_conn_id, tab_title, "SELECT 1;"),
            )
            sqlite_conn.execute(
                "UPDATE OmniDB_app_userdetails SET welcome_closed = 1 WHERE user_id = ?",
                (user_id,),
            )
            sqlite_conn.commit()
    except sqlite3.Error as exc:
        logger.warning("ensure omnidb workspace tab failed: %s", exc)


def sync_connection_to_omnidb(
    conn: Connection,
    *,
    alias: str | None = None,
    ensure_tab: bool = True,
) -> int:
    if not (conn.host or "").strip():
        raise HTTPException(status_code=400, detail="数据库连接未配置主机")

    display_alias = alias or conn.name
    with httpx.Client(
        base_url=settings.omnidb_internal_url.rstrip("/"),
        follow_redirects=True,
        timeout=30,
    ) as client:
        _login_omnidb(client)
        omnidb_id = _find_connection_id_by_alias(client, display_alias)
        omnidb_id = _save_connection_via_api(
            client,
            conn,
            omnidb_id if omnidb_id > 0 else -1,
            alias=display_alias,
        )
        if omnidb_id <= 0:
            raise HTTPException(status_code=502, detail="OmniDB 未能创建连接")
        if ensure_tab:
            _ensure_workspace_tab(omnidb_id, conn.name)
        return omnidb_id


def delete_omnidb_connection(omnidb_id: int) -> None:
    if omnidb_id <= 0:
        return
    with httpx.Client(
        base_url=settings.omnidb_internal_url.rstrip("/"),
        follow_redirects=True,
        timeout=30,
    ) as client:
        _login_omnidb(client)
        csrf = _extract_csrf_token(client)
        response = client.post(
            "/delete_connection/",
            data={"data": json.dumps({"id": omnidb_id})},
            headers={"X-CSRFToken": csrf, "Referer": settings.omnidb_internal_url},
        )
        response.raise_for_status()
        body = response.json()
        if body.get("v_error"):
            raise HTTPException(
                status_code=502,
                detail=f"OmniDB 删除连接失败：{body.get('v_data')}",
            )


def prepare_omnidb_open(
    conn: Connection,
    *,
    public_base: str,
    external_alias: str | None = None,
    ensure_tab: bool = True,
) -> dict:
    omnidb_conn_id = sync_connection_to_omnidb(
        conn,
        alias=external_alias,
        ensure_tab=ensure_tab,
    )
    return {
        "embed_url": build_omnidb_login_url(public_base=public_base),
        "connection_name": conn.name,
        "omnidb_connection_id": omnidb_conn_id,
    }

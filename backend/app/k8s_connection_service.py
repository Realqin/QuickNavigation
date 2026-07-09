"""K8s 连接与日志订阅、集群配置之间的桥接。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.k8s_monitor_service import (
    K8sClusterHttpSession,
    _get_json,
    _normalize_api_server,
    _normalize_auth_type,
    _normalize_provider,
    _uses_kubesphere_password_auth,
)
from app.models import Connection, K8sClusterConfig, Subscription
from app.schemas import ConnectionTestOut

LABEL_K8S = "K8s"

KUBESPHERE_PORTS = {30880, 30443}


@dataclass(frozen=True)
class K8sConnectionEndpoints:
    visit_url: str
    hostname: str
    port: int | None
    api_server: str
    provider: str


def parse_k8s_connection_url(raw: str) -> K8sConnectionEndpoints:
    """从访问地址提取 hostname/port/api_server（供告警与 API 使用）。

    visit_url 为规范化后的等价 URL；展示与跳转应直接使用用户提交的原始 url 字段。
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("集群地址不能为空")

    if not text.startswith(("http://", "https://")):
        text = f"http://{text}"

    parts = urlsplit(text)
    hostname = (parts.hostname or "").strip()
    if not hostname:
        raise ValueError("集群地址格式无效")

    scheme = parts.scheme or "http"
    port = parts.port
    path = parts.path or ""
    visit_url = urlunsplit((scheme, parts.netloc, path, parts.query, parts.fragment))
    if visit_url.endswith("/") and path in ("", "/"):
        visit_url = visit_url.rstrip("/")

    hint = f"{hostname}{path}".lower()
    if "kuboard" in hint:
        provider = "kuboard"
    elif port in KUBESPHERE_PORTS or "kubesphere" in hint:
        provider = "kubesphere"
    else:
        provider = "native"

    origin = f"{scheme}://{parts.netloc}".rstrip("/")
    if provider in {"kubesphere", "kuboard"}:
        api_server = _normalize_api_server(origin)
    elif port is None:
        api_server = _normalize_api_server(f"https://{hostname}:6443")
    else:
        api_server = _normalize_api_server(origin)

    return K8sConnectionEndpoints(
        visit_url=visit_url,
        hostname=hostname,
        port=port,
        api_server=api_server,
        provider=_normalize_provider(provider),
    )


def apply_k8s_connection_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """K8s：url 原样保存用户访问地址；host/port 仅内部解析，不影响展示与跳转。"""
    data = dict(payload)
    raw = str(data.get("url") or data.get("host") or "").strip()
    try:
        parsed = parse_k8s_connection_url(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 展示/跳转用原始地址；仅用户未写 scheme 时补 http://
    if raw.startswith(("http://", "https://")):
        data["url"] = raw
    else:
        data["url"] = parsed.visit_url
    data["host"] = parsed.hostname
    data["port"] = parsed.port
    data["sub_links"] = []
    data["database_name"] = None
    data["mqtt_subscriptions"] = []
    data["mqtt_ws_path"] = None
    return data


def connection_is_k8s_label_name(name: str | None) -> bool:
    text = (name or "").strip().lower()
    return text == LABEL_K8S.lower() or text == "kubernetes"


def _resolve_auth(username: str | None, password: str | None) -> str:
    if password and not username:
        return "token"
    if username:
        return "password"
    return "token"


def get_k8s_cluster_by_connection_id(db: Session, connection_id: int) -> K8sClusterConfig | None:
    return (
        db.query(K8sClusterConfig)
        .filter(K8sClusterConfig.connection_id == connection_id)
        .first()
    )


def sync_k8s_cluster_from_connection(db: Session, conn: Connection) -> K8sClusterConfig | None:
    from app.services import connection_is_k8s_type

    if not connection_is_k8s_type(db, conn):
        return None

    try:
        parsed = parse_k8s_connection_url(str(conn.url or conn.host or ""))
    except ValueError:
        return None

    username = str(conn.username or "").strip() or None
    password = str(conn.password or "").strip() or None
    auth_type = _normalize_auth_type(_resolve_auth(username, password))

    cluster = get_k8s_cluster_by_connection_id(db, conn.id)
    if cluster is None:
        max_order = db.query(func.max(K8sClusterConfig.sort_order)).scalar() or 0
        cluster = K8sClusterConfig(
            name=conn.name.strip(),
            api_server=parsed.api_server,
            provider=parsed.provider,
            auth_type=auth_type,
            username=username,
            password=password,
            verify_ssl=False,
            sort_order=max_order + 1,
            connection_id=conn.id,
        )
        db.add(cluster)
    else:
        cluster.name = conn.name.strip()
        cluster.api_server = parsed.api_server
        cluster.provider = parsed.provider
        cluster.auth_type = auth_type
        cluster.username = username
        if password:
            cluster.password = password

    db.commit()
    db.refresh(cluster)
    return cluster


def test_k8s_connection_payload(
    *,
    host: str,
    username: str | None = None,
    password: str | None = None,
) -> ConnectionTestOut:
    try:
        parsed = parse_k8s_connection_url(host.strip())
    except ValueError as exc:
        return ConnectionTestOut(ok=False, message=str(exc))

    auth_username = (username or "").strip() or None
    auth_password = (password or "").strip() or None
    cluster = K8sClusterConfig(
        name="test",
        api_server=parsed.api_server,
        provider=parsed.provider,
        auth_type=_normalize_auth_type(_resolve_auth(auth_username, auth_password)),
        username=auth_username,
        password=auth_password,
        verify_ssl=False,
    )
    started = time.perf_counter()
    try:
        with K8sClusterHttpSession(cluster) as session:
            _get_json(
                cluster,
                "/api/v1/namespaces",
                force_kubesphere_login=_uses_kubesphere_password_auth(cluster),
                http_client=session.client,
            )
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return ConnectionTestOut(
            ok=True,
            message=(
                f"K8s 连接成功（API: {parsed.api_server}，"
                f"访问: {parsed.visit_url}）"
            ),
            latency_ms=latency_ms,
        )
    except HTTPException as exc:
        return ConnectionTestOut(ok=False, message=str(exc.detail))
    except Exception as exc:
        return ConnectionTestOut(ok=False, message=f"连接失败：{exc}")


def validate_k8s_subscription_enable(db: Session, conn: Connection) -> None:
    cluster = sync_k8s_cluster_from_connection(db, conn)
    if not cluster:
        raise HTTPException(status_code=400, detail="K8s 集群配置未同步，请先完善连接信息")
    from app.k8s_monitor_service import test_k8s_cluster_connection

    try:
        test_k8s_cluster_connection(db, cluster)
    except HTTPException as exc:
        raise HTTPException(status_code=400, detail=str(exc.detail)) from exc


def build_k8s_subscription_links(
    conn: Connection,
    sub: Subscription,
    link_enabled: dict[str, bool] | None,
    *,
    cluster_id: int | None,
) -> list[dict[str, Any]]:
    states = link_enabled or {}
    enabled = bool(states.get("main", False))
    visit_url = str(conn.url or conn.host or "").strip()
    return [
        {
            "link_key": "main",
            "name": "主链接",
            "url": visit_url,
            "clone_url": "",
            "branch": "-",
            "repo_path": "",
            "enabled": enabled,
            "link_kind": "k8s",
            "cluster_id": cluster_id,
            "has_webhook_secret": bool(sub.webhook_secret),
        }
    ]


def is_k8s_subscription_enabled(sub: Subscription) -> bool:
    if not sub.enabled:
        return False
    states = sub.link_enabled or {}
    return bool(states.get("main", False))

from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.k8s_monitor_service import (
    K8sClusterHttpSession,
    get_k8s_cluster,
    list_k8s_projects,
    list_k8s_services,
)
from app.models import K8sAlarmMonitorGroup, K8sAlarmMonitorService, K8sClusterConfig
from app.schemas import K8sAlarmMonitorGroupUpdate, K8sAlarmMonitorServiceUpdate

RESTART_MONITOR_OPTIONS = {"none", "immediate", "5m", "10m"}


def _normalize_restart_monitor(value: str | None) -> str:
    text = (value or "none").strip()
    return text if text in RESTART_MONITOR_OPTIONS else "none"


def _service_row_out(row: K8sAlarmMonitorService) -> dict[str, Any]:
    return {
        "service_name": row.service_name,
        "restart_monitor": _normalize_restart_monitor(row.restart_monitor),
        "watermark_minutes": row.watermark_minutes,
    }


def _namespace_service_stats(db: Session, cluster_id: int) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    rows = (
        db.query(K8sAlarmMonitorService)
        .filter(K8sAlarmMonitorService.cluster_id == cluster_id)
        .all()
    )
    for item in rows:
        bucket = stats.setdefault(item.namespace, {"total": 0, "monitored": 0})
        bucket["total"] += 1
        if item.restart_monitor != "none" or item.watermark_minutes is not None:
            bucket["monitored"] += 1
    return stats


def _group_row_out(
    group: K8sAlarmMonitorGroup,
    stats: dict[str, dict[str, int]],
) -> dict[str, Any]:
    namespace_stats = stats.get(group.namespace, {"total": 0, "monitored": 0})
    return {
        "namespace": group.namespace,
        "enabled": bool(group.enabled),
        "service_count": namespace_stats["total"],
        "monitored_service_count": namespace_stats["monitored"],
    }


def _get_or_create_group(
    db: Session,
    cluster_id: int,
    namespace: str,
    *,
    commit: bool = True,
) -> K8sAlarmMonitorGroup:
    row = (
        db.query(K8sAlarmMonitorGroup)
        .filter(
            K8sAlarmMonitorGroup.cluster_id == cluster_id,
            K8sAlarmMonitorGroup.namespace == namespace,
        )
        .first()
    )
    if row:
        return row
    row = K8sAlarmMonitorGroup(cluster_id=cluster_id, namespace=namespace, enabled=False)
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def _sync_namespace_services(
    db: Session,
    cluster: K8sClusterConfig,
    namespace: str,
    *,
    http_client: httpx.Client | None = None,
) -> int:
    live_services = list_k8s_services(
        cluster,
        namespace,
        http_client=http_client,
        include_pods=False,
    )
    live_names = sorted(
        {
            str(item.get("service_name") or "").strip()
            for item in live_services
            if item.get("service_name")
        }
    )
    existing_rows = (
        db.query(K8sAlarmMonitorService)
        .filter(
            K8sAlarmMonitorService.cluster_id == cluster.id,
            K8sAlarmMonitorService.namespace == namespace,
        )
        .all()
    )
    existing_map = {row.service_name: row for row in existing_rows}
    live_set = set(live_names)

    for service_name in live_names:
        if service_name not in existing_map:
            db.add(
                K8sAlarmMonitorService(
                    cluster_id=cluster.id,
                    namespace=namespace,
                    service_name=service_name,
                    restart_monitor="none",
                    watermark_minutes=None,
                )
            )

    for row in existing_rows:
        if row.service_name not in live_set:
            db.delete(row)

    return len(live_names)


def _remove_stale_groups(db: Session, cluster_id: int, live_namespaces: set[str]) -> None:
    stale_groups = (
        db.query(K8sAlarmMonitorGroup)
        .filter(K8sAlarmMonitorGroup.cluster_id == cluster_id)
        .all()
    )
    for group in stale_groups:
        if group.namespace in live_namespaces:
            continue
        (
            db.query(K8sAlarmMonitorService)
            .filter(
                K8sAlarmMonitorService.cluster_id == cluster_id,
                K8sAlarmMonitorService.namespace == group.namespace,
            )
            .delete(synchronize_session=False)
        )
        db.delete(group)


def _sync_alarm_monitor_groups(
    db: Session,
    cluster: K8sClusterConfig,
    *,
    http_client: httpx.Client,
) -> list[str]:
    """仅拉取项目/命名空间列表并入库，不逐个同步服务。"""
    projects = list_k8s_projects(cluster, http_client=http_client)
    namespaces: list[str] = []
    for project in projects:
        name = str(project.get("name") or "").strip()
        if not name:
            continue
        _get_or_create_group(db, cluster.id, name, commit=False)
        namespaces.append(name)

    _remove_stale_groups(db, cluster.id, set(namespaces))
    db.commit()
    return namespaces


def sync_alarm_monitor_data(
    db: Session,
    cluster: K8sClusterConfig,
    *,
    namespace: str | None = None,
) -> dict[str, Any]:
    if namespace:
        namespace = namespace.strip()
        if not namespace:
            raise HTTPException(status_code=400, detail="分组名称不能为空")
        with K8sClusterHttpSession(cluster) as session:
            _get_or_create_group(db, cluster.id, namespace, commit=False)
            services_count = _sync_namespace_services(
                db,
                cluster,
                namespace,
                http_client=session.client,
            )
        db.commit()
        return {
            "groups_count": 1,
            "services_count": services_count,
            "namespaces": [namespace],
        }

    with K8sClusterHttpSession(cluster) as session:
        namespaces = _sync_alarm_monitor_groups(db, cluster, http_client=session.client)

    return {
        "groups_count": len(namespaces),
        "services_count": 0,
        "namespaces": sorted(namespaces),
    }


def list_alarm_monitor_groups(db: Session, cluster: K8sClusterConfig) -> list[dict[str, Any]]:
    stats = _namespace_service_stats(db, cluster.id)
    groups = (
        db.query(K8sAlarmMonitorGroup)
        .filter(K8sAlarmMonitorGroup.cluster_id == cluster.id)
        .order_by(K8sAlarmMonitorGroup.namespace.asc())
        .all()
    )
    return [_group_row_out(group, stats) for group in groups]


def update_alarm_monitor_group(
    db: Session,
    cluster: K8sClusterConfig,
    namespace: str,
    data: K8sAlarmMonitorGroupUpdate,
) -> dict[str, Any]:
    namespace = namespace.strip()
    if not namespace:
        raise HTTPException(status_code=400, detail="分组名称不能为空")
    row = _get_or_create_group(db, cluster.id, namespace)
    row.enabled = bool(data.enabled)
    db.commit()
    db.refresh(row)
    stats = _namespace_service_stats(db, cluster.id)
    return _group_row_out(row, stats)


def list_alarm_monitor_services(
    db: Session,
    cluster: K8sClusterConfig,
    namespace: str,
) -> list[dict[str, Any]]:
    namespace = namespace.strip()
    if not namespace:
        raise HTTPException(status_code=400, detail="分组名称不能为空")

    rows = (
        db.query(K8sAlarmMonitorService)
        .filter(
            K8sAlarmMonitorService.cluster_id == cluster.id,
            K8sAlarmMonitorService.namespace == namespace,
        )
        .order_by(K8sAlarmMonitorService.service_name.asc())
        .all()
    )
    return [_service_row_out(row) for row in rows]


def update_alarm_monitor_service(
    db: Session,
    cluster: K8sClusterConfig,
    namespace: str,
    service_name: str,
    data: K8sAlarmMonitorServiceUpdate,
) -> dict[str, Any]:
    namespace = namespace.strip()
    service_name = service_name.strip()
    if not namespace or not service_name:
        raise HTTPException(status_code=400, detail="分组与服务名称不能为空")

    row = (
        db.query(K8sAlarmMonitorService)
        .filter(
            K8sAlarmMonitorService.cluster_id == cluster.id,
            K8sAlarmMonitorService.namespace == namespace,
            K8sAlarmMonitorService.service_name == service_name,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="服务监控配置不存在，请先同步服务列表")

    row.restart_monitor = _normalize_restart_monitor(data.restart_monitor)
    row.watermark_minutes = data.watermark_minutes
    db.commit()
    db.refresh(row)
    return _service_row_out(row)


def get_alarm_monitor_cluster(db: Session, cluster_id: int) -> K8sClusterConfig:
    return get_k8s_cluster(db, cluster_id)

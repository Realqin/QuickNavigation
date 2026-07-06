import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.k8s_monitor_service import (
    FlinkHttpClientPool,
    K8sClusterHttpSession,
    _pod_container_restart_map,
    probe_k8s_service_for_alarm,
    read_k8s_service_exceptions,
    read_k8s_service_watermarks,
)
from app.models import (
    K8sAlarmEvent,
    K8sAlarmMonitorGroup,
    K8sAlarmMonitorService,
    K8sAlarmMonitorSnapshot,
    K8sClusterConfig,
)
from app.schemas import K8sAlarmEventOut
from app.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

RESTART_WINDOW_MINUTES = {"5m": 5, "10m": 10}
TARGET_CHECK_INTERVAL_SECONDS = 0.2

_BEIJING_TZ = timezone(timedelta(hours=8))
_EXCEPTION_TIME_FORMATTER = "%Y-%m-%d %H:%M:%S"


def _format_beijing_time(timestamp_ms: int | None) -> str:
    if not timestamp_ms or timestamp_ms <= 0:
        return "-"
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=_BEIJING_TZ).strftime(
            _EXCEPTION_TIME_FORMATTER
        )
    except (OverflowError, OSError, ValueError):
        return "-"


def _is_buffer_exhausted_detail(detail: Any) -> bool:
    text = str(detail).lower()
    return any(
        marker in text
        for marker in ("no buffer space", "enobufs", "10055", "网络缓冲区不足")
    )


def _normalize_restart_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, count in value.items():
        text = str(key).strip()
        if not text:
            continue
        try:
            result[text] = int(count or 0)
        except (TypeError, ValueError):
            continue
    return result


def detect_restart_increase(
    previous: dict[str, int] | None,
    current: dict[str, int],
    *,
    is_baseline: bool,
) -> tuple[bool, list[str]]:
    """对比 pod/container 级 restartCount，仅在实际增量时视为重启。"""
    if is_baseline:
        return False, []
    prev = previous or {}
    increased_keys: list[str] = []
    for key, count in current.items():
        prev_count = prev.get(key)
        if prev_count is not None and count > prev_count:
            increased_keys.append(key)
        elif prev_count is None and count > 0:
            # 新 Pod/容器在首次被监控时已发生重启
            increased_keys.append(key)
    return bool(increased_keys), increased_keys


def _format_restart_increase_summary(increased_keys: list[str], current: dict[str, int]) -> str:
    if not increased_keys:
        return "检测到容器重启"
    parts: list[str] = []
    for key in increased_keys[:3]:
        prev_hint = current.get(key, 0)
        parts.append(f"{key} → {prev_hint} 次")
    suffix = f" 等 {len(increased_keys)} 处" if len(increased_keys) > 3 else ""
    return f"检测到容器重启：{', '.join(parts)}{suffix}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _event_out(event: K8sAlarmEvent, cluster_name: str = "") -> dict[str, Any]:
    return K8sAlarmEventOut(
        id=event.id,
        cluster_id=event.cluster_id,
        cluster_name=cluster_name,
        namespace=event.namespace,
        service_name=event.service_name,
        alert_type=event.alert_type,
        status=event.status,
        title=event.title,
        summary=event.summary,
        payload=event.payload,
        is_read=event.is_read,
        occurred_at=event.occurred_at,
        resolved_at=event.resolved_at,
    ).model_dump(mode="json")


async def _broadcast_alarm(db: Session, event: K8sAlarmEvent, cluster_name: str) -> None:
    await ws_manager.broadcast(
        {"type": "k8s-alarm:new", "data": _event_out(event, cluster_name)},
    )

    from app.k8s_connection_service import is_k8s_subscription_enabled
    from app.models import Connection, K8sClusterConfig
    from app.schemas import ActivityLogOut
    from app.services import _primary_project_environment, create_activity_log

    cluster = db.query(K8sClusterConfig).filter(K8sClusterConfig.id == event.cluster_id).first()
    if not cluster or not cluster.connection_id:
        return
    conn = db.query(Connection).filter(Connection.id == cluster.connection_id).first()
    if not conn or not conn.subscription or not is_k8s_subscription_enabled(conn.subscription):
        return

    project, environment = _primary_project_environment(db, conn)
    log = create_activity_log(
        db,
        subscription_id=conn.subscription.id,
        connection_id=conn.id,
        project=project,
        environment=environment,
        source_type="k8s",
        title=event.title,
        summary=event.summary,
        payload={
            "event": "k8s_alarm",
            "alert_type": event.alert_type,
            "status": event.status,
            "namespace": event.namespace,
            "service_name": event.service_name,
            "cluster_id": event.cluster_id,
            "cluster_name": cluster_name,
            **(event.payload or {}),
        },
        author="k8s-alarm-monitor",
    )
    data = ActivityLogOut.model_validate(log).model_dump(mode="json")
    await ws_manager.broadcast({"type": "log:new", "data": data})


def list_k8s_alarm_events(
    db: Session,
    cluster_id: int,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    cluster = db.query(K8sClusterConfig).filter(K8sClusterConfig.id == cluster_id).first()
    cluster_name = cluster.name if cluster else ""
    query = db.query(K8sAlarmEvent).filter(K8sAlarmEvent.cluster_id == cluster_id)
    if status:
        query = query.filter(K8sAlarmEvent.status == status.strip())
    events = query.order_by(K8sAlarmEvent.occurred_at.desc()).limit(max(1, min(limit, 200))).all()
    return [_event_out(event, cluster_name) for event in events]


def count_unread_k8s_alarm_events(db: Session, cluster_id: int) -> int:
    return (
        db.query(K8sAlarmEvent)
        .filter(
            K8sAlarmEvent.cluster_id == cluster_id,
            K8sAlarmEvent.status == "firing",
            K8sAlarmEvent.is_read.is_(False),
        )
        .count()
    )


def mark_k8s_alarm_event_read(db: Session, event_id: int) -> dict[str, Any]:
    event = db.query(K8sAlarmEvent).filter(K8sAlarmEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="告警不存在")
    event.is_read = True
    db.commit()
    db.refresh(event)
    cluster = db.query(K8sClusterConfig).filter(K8sClusterConfig.id == event.cluster_id).first()
    return _event_out(event, cluster.name if cluster else "")


def mark_k8s_alarm_events_read_all(db: Session, cluster_id: int) -> int:
    updated = (
        db.query(K8sAlarmEvent)
        .filter(
            K8sAlarmEvent.cluster_id == cluster_id,
            K8sAlarmEvent.is_read.is_(False),
        )
        .update({K8sAlarmEvent.is_read: True}, synchronize_session=False)
    )
    db.commit()
    return int(updated or 0)


def _list_monitor_targets(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(K8sAlarmMonitorService, K8sAlarmMonitorGroup, K8sClusterConfig)
        .join(
            K8sAlarmMonitorGroup,
            and_(
                K8sAlarmMonitorGroup.cluster_id == K8sAlarmMonitorService.cluster_id,
                K8sAlarmMonitorGroup.namespace == K8sAlarmMonitorService.namespace,
            ),
        )
        .join(K8sClusterConfig, K8sClusterConfig.id == K8sAlarmMonitorService.cluster_id)
        .filter(K8sAlarmMonitorGroup.enabled.is_(True))
        .filter(
            or_(
                K8sAlarmMonitorService.restart_monitor != "none",
                K8sAlarmMonitorService.watermark_minutes.isnot(None),
            )
        )
        .all()
    )
    targets: list[dict[str, Any]] = []
    for service_row, _group_row, cluster in rows:
        targets.append(
            {
                "cluster": cluster,
                "namespace": service_row.namespace,
                "service_name": service_row.service_name,
                "restart_monitor": service_row.restart_monitor,
                "watermark_minutes": service_row.watermark_minutes,
            }
        )
    return targets


def _get_or_create_snapshot(
    db: Session,
    cluster_id: int,
    namespace: str,
    service_name: str,
) -> K8sAlarmMonitorSnapshot:
    row = (
        db.query(K8sAlarmMonitorSnapshot)
        .filter(
            K8sAlarmMonitorSnapshot.cluster_id == cluster_id,
            K8sAlarmMonitorSnapshot.namespace == namespace,
            K8sAlarmMonitorSnapshot.service_name == service_name,
        )
        .first()
    )
    if row:
        return row
    row = K8sAlarmMonitorSnapshot(
        cluster_id=cluster_id,
        namespace=namespace,
        service_name=service_name,
    )
    db.add(row)
    db.flush()
    return row


def _max_watermark_lag_ms(result: dict[str, Any]) -> int | None:
    max_lag: int | None = None
    for item in result.get("items") or []:
        for watermark in item.get("watermarks") or []:
            lag = int(watermark.get("lag_ms") or 0)
            if max_lag is None or lag > max_lag:
                max_lag = lag
    return max_lag


def _watermark_operators_summary(result: dict[str, Any]) -> list[dict[str, Any]]:
    """精简算子 Watermark 明细，用于写入告警 payload 供详情展示。"""
    operators: list[dict[str, Any]] = []
    for item in result.get("items") or []:
        watermarks = []
        for watermark in item.get("watermarks") or []:
            watermarks.append(
                {
                    "raw": watermark.get("raw"),
                    "timestamp": watermark.get("timestamp"),
                    "lag_ms": int(watermark.get("lag_ms") or 0),
                }
            )
        operators.append(
            {
                "operator_name": item.get("operator_name") or item.get("vertex_id") or "",
                "job_name": item.get("job_name") or "",
                "error": item.get("error") or "",
                "watermarks": watermarks,
            }
        )
    return operators


def _restart_should_fire(
    rule: str,
    *,
    increased: bool,
    last_restart_at: datetime | None,
    now: datetime,
) -> bool:
    if rule == "none":
        return False
    if rule == "immediate":
        return increased
    window = RESTART_WINDOW_MINUTES.get(rule)
    if not window or not last_restart_at:
        return False
    return now - last_restart_at <= timedelta(minutes=window)


def _service_link_meta(probe: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    ports = probe.get("external_ports") or []
    if ports:
        meta["external_ports"] = ports
    if probe.get("workload_kind"):
        meta["workload_kind"] = probe["workload_kind"]
    if probe.get("workload_name"):
        meta["workload_name"] = probe["workload_name"]
    return meta


def _emit_alarm_event(
    db: Session,
    *,
    cluster: K8sClusterConfig,
    namespace: str,
    service_name: str,
    alert_type: str,
    status: str,
    title: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    link_meta: dict[str, Any] | None = None,
) -> K8sAlarmEvent:
    merged_payload: dict[str, Any] | None = None
    if link_meta or payload:
        merged_payload = {**(link_meta or {}), **(payload or {})}
    now = _utcnow()
    event = K8sAlarmEvent(
        cluster_id=cluster.id,
        namespace=namespace,
        service_name=service_name,
        alert_type=alert_type,
        status=status,
        title=title,
        summary=summary,
        payload=merged_payload,
        is_read=False,
        occurred_at=now,
        resolved_at=now if status == "resolved" else None,
    )
    db.add(event)
    db.flush()
    return event


def _evaluate_restart(
    db: Session,
    *,
    cluster: K8sClusterConfig,
    namespace: str,
    service_name: str,
    rule: str,
    current_restart_count: int,
    increased: bool,
    increased_keys: list[str],
    current_restart_map: dict[str, int],
    snapshot: K8sAlarmMonitorSnapshot,
    now: datetime,
    pending_broadcasts: list[tuple[K8sAlarmEvent, str]],
    link_meta: dict[str, Any] | None = None,
) -> None:
    should_fire = _restart_should_fire(
        rule,
        increased=increased,
        last_restart_at=snapshot.last_restart_at,
        now=now,
    )

    if should_fire and not snapshot.restart_alert_active:
        summary = _format_restart_increase_summary(increased_keys, current_restart_map)
        if current_restart_count:
            summary = f"{summary}（累计 {current_restart_count} 次）"
        event = _emit_alarm_event(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            alert_type="restart",
            status="firing",
            title=f"服务重启告警 · {service_name}",
            summary=summary,
            payload={
                "restart_monitor": rule,
                "restart_count": current_restart_count,
                "increased_keys": increased_keys,
                "restart_map": current_restart_map,
                "last_restart_at": snapshot.last_restart_at.isoformat()
                if snapshot.last_restart_at
                else None,
            },
            link_meta=link_meta,
        )
        snapshot.restart_alert_active = True
        pending_broadcasts.append((event, cluster.name))
        return

    if snapshot.restart_alert_active and not should_fire:
        event = _emit_alarm_event(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            alert_type="restart",
            status="resolved",
            title=f"服务重启恢复 · {service_name}",
            summary="重启监控已恢复正常",
            payload={"restart_monitor": rule, "restart_count": current_restart_count},
            link_meta=link_meta,
        )
        snapshot.restart_alert_active = False
        pending_broadcasts.append((event, cluster.name))


def _evaluate_watermark(
    db: Session,
    *,
    cluster: K8sClusterConfig,
    namespace: str,
    service_name: str,
    threshold_minutes: int,
    live_service: dict[str, Any] | None,
    snapshot: K8sAlarmMonitorSnapshot,
    pending_broadcasts: list[tuple[K8sAlarmEvent, str]],
    flink_pool: FlinkHttpClientPool | None = None,
    link_meta: dict[str, Any] | None = None,
) -> None:
    external_ports = (live_service or {}).get("external_ports") or []
    port = external_ports[0] if external_ports else None
    if not port:
        if snapshot.watermark_alert_active:
            event = _emit_alarm_event(
                db,
                cluster=cluster,
                namespace=namespace,
                service_name=service_name,
                alert_type="watermark",
                status="resolved",
                title=f"Watermark 恢复 · {service_name}",
                summary="服务无外部端口，跳过 Watermark 监控",
                link_meta=link_meta,
            )
            snapshot.watermark_alert_active = False
            pending_broadcasts.append((event, cluster.name))
        snapshot.max_watermark_lag_ms = None
        return

    try:
        flink_client = flink_pool.client_for_port(int(port)) if flink_pool else None
        result = read_k8s_service_watermarks(
            cluster,
            namespace=namespace,
            service_name=service_name,
            port=int(port),
            http_client=flink_client,
        )
        max_lag = _max_watermark_lag_ms(result)
    except HTTPException as exc:
        if _is_buffer_exhausted_detail(exc.detail):
            raise
        logger.warning(
            "Watermark check failed cluster=%s service=%s: %s",
            cluster.id,
            service_name,
            exc.detail,
        )
        return

    snapshot.max_watermark_lag_ms = max_lag
    threshold_ms = int(threshold_minutes) * 60 * 1000
    should_fire = max_lag is not None and max_lag > threshold_ms
    operators_summary = _watermark_operators_summary(result)

    if should_fire and not snapshot.watermark_alert_active:
        lag_minutes = round(max_lag / 60000, 1)
        event = _emit_alarm_event(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            alert_type="watermark",
            status="firing",
            title=f"Watermark 延迟告警 · {service_name}",
            summary=f"Watermark 延迟 {lag_minutes} 分钟，超过阈值 {threshold_minutes} 分钟",
            payload={
                "watermark_minutes": threshold_minutes,
                "lag_ms": max_lag,
                "port": int(port),
                "operators": operators_summary,
            },
            link_meta=link_meta,
        )
        snapshot.watermark_alert_active = True
        pending_broadcasts.append((event, cluster.name))
        return

    if snapshot.watermark_alert_active and not should_fire:
        event = _emit_alarm_event(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            alert_type="watermark",
            status="resolved",
            title=f"Watermark 恢复 · {service_name}",
            summary="Watermark 延迟已回到阈值内",
            payload={
                "watermark_minutes": threshold_minutes,
                "lag_ms": max_lag,
                "port": int(port),
                "operators": operators_summary,
            },
            link_meta=link_meta,
        )
        snapshot.watermark_alert_active = False
        pending_broadcasts.append((event, cluster.name))


def _pick_latest_exception(result: dict[str, Any]) -> tuple[dict[str, Any] | None, int]:
    """返回 (最新异常所在的 job 项, 最新异常 timestamp)。无异常时返回 (None, 0)。"""
    latest_job: dict[str, Any] | None = None
    latest_ts = 0
    for job in result.get("items") or []:
        ts = int(job.get("latest_timestamp") or 0)
        if ts > latest_ts:
            latest_ts = ts
            latest_job = job
    return latest_job, latest_ts


def _build_exception_summary(job: dict[str, Any], timestamp_ms: int) -> str:
    job_name = job.get("job_name") or ""
    time_text = _format_beijing_time(timestamp_ms)
    root = str(job.get("root_exception") or "").strip()
    if root:
        first_line = root.splitlines()[0][:160]
    else:
        first_line = "检测到作业异常"
    prefix = f"[{job_name}] " if job_name else ""
    return f"{prefix}{first_line}（异常时间 {time_text}）"


def _evaluate_exception(
    db: Session,
    *,
    cluster: K8sClusterConfig,
    namespace: str,
    service_name: str,
    port: int,
    snapshot: K8sAlarmMonitorSnapshot,
    pending_broadcasts: list[tuple[K8sAlarmEvent, str]],
    flink_pool: FlinkHttpClientPool | None = None,
    link_meta: dict[str, Any] | None = None,
) -> None:
    """对配置了 Watermark 监控的服务，额外监控 Flink 作业异常日志。

    基线（last_exception_timestamp 为 None）只记录不告警，避免对历史异常误报。
    """
    try:
        flink_client = flink_pool.client_for_port(int(port)) if flink_pool else None
        result = read_k8s_service_exceptions(
            cluster,
            namespace=namespace,
            service_name=service_name,
            port=int(port),
            http_client=flink_client,
        )
    except HTTPException as exc:
        if _is_buffer_exhausted_detail(exc.detail):
            raise
        logger.warning(
            "Exception check failed cluster=%s service=%s: %s",
            cluster.id,
            service_name,
            exc.detail,
        )
        return

    latest_job, latest_ts = _pick_latest_exception(result)
    is_baseline = snapshot.last_exception_timestamp is None

    if latest_ts <= 0:
        # 无异常：若之前在告警中则恢复，并重置基线以便下次出现异常重新感知
        if snapshot.exception_alert_active:
            event = _emit_alarm_event(
                db,
                cluster=cluster,
                namespace=namespace,
                service_name=service_name,
                alert_type="exception",
                status="resolved",
                title=f"作业异常恢复 · {service_name}",
                summary="Flink 作业异常历史已清空",
                payload={"port": int(port)},
                link_meta=link_meta,
            )
            snapshot.exception_alert_active = False
            pending_broadcasts.append((event, cluster.name))
        snapshot.last_exception_timestamp = None
        return

    if is_baseline:
        snapshot.last_exception_timestamp = latest_ts
        return

    if latest_ts > int(snapshot.last_exception_timestamp or 0):
        summary = _build_exception_summary(latest_job or {}, latest_ts)
        event = _emit_alarm_event(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            alert_type="exception",
            status="firing",
            title=f"作业异常告警 · {service_name}",
            summary=summary,
            payload={
                "port": int(port),
                "job_id": (latest_job or {}).get("job_id"),
                "job_name": (latest_job or {}).get("job_name"),
                "exception": (latest_job or {}).get("root_exception"),
                "exception_timestamp": latest_ts,
                "exception_time_beijing": _format_beijing_time(latest_ts),
                "exception_count": int((latest_job or {}).get("exception_count") or 0),
                "jobs": [
                    {
                        "job_id": job.get("job_id"),
                        "job_name": job.get("job_name"),
                        "exception_count": int(job.get("exception_count") or 0),
                        "latest_timestamp": int(job.get("latest_timestamp") or 0),
                        "exceptions": job.get("exceptions") or [],
                    }
                    for job in (result.get("items") or [])
                ],
            },
            link_meta=link_meta,
        )
        snapshot.last_exception_timestamp = latest_ts
        snapshot.exception_alert_active = True
        pending_broadcasts.append((event, cluster.name))


def _evaluate_single_target(
    db: Session,
    target: dict[str, Any],
    *,
    http_client: httpx.Client | None = None,
    flink_pool: FlinkHttpClientPool | None = None,
) -> list[tuple[K8sAlarmEvent, str]]:
    cluster: K8sClusterConfig = target["cluster"]
    namespace = target["namespace"]
    service_name = target["service_name"]
    now = _utcnow()
    pending_broadcasts: list[tuple[K8sAlarmEvent, str]] = []

    if http_client is not None:
        probe = probe_k8s_service_for_alarm(
            cluster,
            namespace,
            service_name,
            http_client=http_client,
        )
    else:
        with K8sClusterHttpSession(cluster) as session:
            probe = probe_k8s_service_for_alarm(
                cluster,
                namespace,
                service_name,
                http_client=session.client,
            )

    live_service = {
        "external_ports": probe.get("external_ports") or [],
        "pods": probe.get("pods") or [],
    }
    link_meta = _service_link_meta(probe)
    snapshot = _get_or_create_snapshot(db, cluster.id, namespace, service_name)
    is_baseline = (
        snapshot.last_checked_at is None or snapshot.pod_restart_snapshot is None
    )
    snapshot.last_checked_at = now

    current_restart_map = _normalize_restart_map(probe.get("restart_map"))
    if not current_restart_map:
        current_restart_map = _pod_container_restart_map(probe.get("pods") or [])
    previous_restart_map = _normalize_restart_map(snapshot.pod_restart_snapshot)
    current_restart_count = int(probe.get("restart_count") or 0)
    if not current_restart_count and current_restart_map:
        current_restart_count = sum(current_restart_map.values())

    restart_increased, increased_keys = detect_restart_increase(
        previous_restart_map,
        current_restart_map,
        is_baseline=is_baseline,
    )
    if restart_increased:
        snapshot.last_restart_at = now
    snapshot.restart_count_snapshot = current_restart_count
    snapshot.pod_restart_snapshot = current_restart_map

    restart_rule = target["restart_monitor"] or "none"
    if restart_rule != "none" and not is_baseline:
        _evaluate_restart(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            rule=restart_rule,
            current_restart_count=current_restart_count,
            increased=restart_increased,
            increased_keys=increased_keys,
            current_restart_map=current_restart_map,
            snapshot=snapshot,
            now=now,
            pending_broadcasts=pending_broadcasts,
            link_meta=link_meta,
        )
    elif snapshot.restart_alert_active:
        event = _emit_alarm_event(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            alert_type="restart",
            status="resolved",
            title=f"服务重启恢复 · {service_name}",
            summary="已关闭重启监控规则",
            link_meta=link_meta,
        )
        snapshot.restart_alert_active = False
        pending_broadcasts.append((event, cluster.name))

    watermark_minutes = target["watermark_minutes"]
    if watermark_minutes:
        _evaluate_watermark(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            threshold_minutes=int(watermark_minutes),
            live_service=live_service,
            snapshot=snapshot,
            pending_broadcasts=pending_broadcasts,
            flink_pool=flink_pool,
            link_meta=link_meta,
        )
        external_ports = live_service.get("external_ports") or []
        exception_port = external_ports[0] if external_ports else None
        if exception_port:
            _evaluate_exception(
                db,
                cluster=cluster,
                namespace=namespace,
                service_name=service_name,
                port=int(exception_port),
                snapshot=snapshot,
                pending_broadcasts=pending_broadcasts,
                flink_pool=flink_pool,
                link_meta=link_meta,
            )
        elif snapshot.exception_alert_active:
            event = _emit_alarm_event(
                db,
                cluster=cluster,
                namespace=namespace,
                service_name=service_name,
                alert_type="exception",
                status="resolved",
                title=f"作业异常恢复 · {service_name}",
                summary="服务无外部端口，跳过作业异常监控",
                link_meta=link_meta,
            )
            snapshot.exception_alert_active = False
            pending_broadcasts.append((event, cluster.name))
    elif snapshot.watermark_alert_active:
        event = _emit_alarm_event(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            alert_type="watermark",
            status="resolved",
            title=f"Watermark 恢复 · {service_name}",
            summary="已关闭 Watermark 监控规则",
            link_meta=link_meta,
        )
        snapshot.watermark_alert_active = False
        pending_broadcasts.append((event, cluster.name))
    if not watermark_minutes and snapshot.exception_alert_active:
        event = _emit_alarm_event(
            db,
            cluster=cluster,
            namespace=namespace,
            service_name=service_name,
            alert_type="exception",
            status="resolved",
            title=f"作业异常恢复 · {service_name}",
            summary="已关闭 Watermark 监控，作业异常监控一并关闭",
            link_meta=link_meta,
        )
        snapshot.exception_alert_active = False
        snapshot.last_exception_timestamp = None
        pending_broadcasts.append((event, cluster.name))

    db.commit()
    return pending_broadcasts


def run_k8s_alarm_evaluation(db: Session) -> list[tuple[K8sAlarmEvent, str]]:
    targets = _list_monitor_targets(db)
    broadcasts: list[tuple[K8sAlarmEvent, str]] = []
    targets_by_cluster: dict[int, list[dict[str, Any]]] = {}
    for target in targets:
        targets_by_cluster.setdefault(target["cluster"].id, []).append(target)

    processed = 0
    for cluster_targets in targets_by_cluster.values():
        cluster: K8sClusterConfig = cluster_targets[0]["cluster"]
        with K8sClusterHttpSession(cluster) as session, FlinkHttpClientPool(cluster) as flink_pool:
            for target in cluster_targets:
                try:
                    broadcasts.extend(
                        _evaluate_single_target(
                            db,
                            target,
                            http_client=session.client,
                            flink_pool=flink_pool,
                        )
                    )
                except HTTPException as exc:
                    if _is_buffer_exhausted_detail(exc.detail):
                        logger.error(
                            "Network buffer exhausted, aborting k8s alarm evaluation: %s",
                            exc.detail,
                        )
                        return broadcasts
                    logger.warning(
                        "Alarm check skipped cluster=%s namespace=%s service=%s: %s",
                        target["cluster"].id,
                        target["namespace"],
                        target["service_name"],
                        exc.detail,
                    )
                    db.rollback()
                except Exception:
                    logger.exception(
                        "Alarm check failed cluster=%s namespace=%s service=%s",
                        target["cluster"].id,
                        target["namespace"],
                        target["service_name"],
                    )
                    db.rollback()
                processed += 1
                if processed < len(targets):
                    time.sleep(TARGET_CHECK_INTERVAL_SECONDS)
    return broadcasts


async def evaluate_k8s_alarms_async(db: Session) -> None:
    broadcasts = await asyncio.to_thread(run_k8s_alarm_evaluation, db)
    for event, cluster_name in broadcasts:
        try:
            await _broadcast_alarm(db, event, cluster_name)
        except Exception:
            logger.exception("Broadcast k8s alarm failed event=%s", event.id)

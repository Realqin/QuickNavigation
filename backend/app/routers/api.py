from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.database import get_db
from app.repo_access_config import get_public_webhook_base_url
from app.models import Connection, DictItem, Subscription
from app.schemas import (
    ApiMonitorEndpointChangeOut,
    ApiMonitorEndpointOut,
    ApiMonitorGroupEndpointsOut,
    ApiMonitorGroupOut,
    ApiMonitorGroupsOut,
    ApiMonitorModulesOut,
    ApiMonitorFilterOptionsOut,
    ApiMonitorProxyIn,
    ApiMonitorProxyOut,
    ApiMonitorScanRunChangesOut,
    ApiMonitorScanRunOut,
    ApiMonitorServiceOut,
    ApiMonitorSpecOut,
    ApiMonitorSyncResultOut,
    AiAnalysisIn,
    AiAnalysisOut,
    ApiTestCaseCreate,
    ApiTestCaseBatchDeleteOut,
    ApiTestCaseExecutionResultIn,
    ApiTestCaseGenerateIn,
    ApiTestCaseGenerateOut,
    ApiTestCaseListOut,
    ApiTestCaseOut,
    ApiTestCaseUpdate,
    LlmConfigCreate,
    LlmConfigOut,
    LlmConfigUpdate,
    LlmConnectionTestIn,
    LlmConnectionTestOut,
    LlmModelsFetchIn,
    LlmModelsOut,
    LlmToggleIn,
    PromptTemplateIn,
    PromptTemplateOut,
    ActivityLogDiffOut,
    ActivityLogOut,
    BatchDeleteRequest,
    ConnectionCreate,
    ConnectionOut,
    ConnectionTestOut,
    ConnectionTestRequest,
    ConnectionUpdate,
    DictItemCreate,
    DictItemOut,
    DictItemUpdate,
    GitlabSubscriptionTreeOut,
    HomeResponse,
    KafkaConsoleConnectionCreate,
    KafkaConsoleConnectionOut,
    KafkaConsoleConnectionTestRequest,
    KafkaConsoleConnectionUpdate,
    K8sAlarmMonitorGroupOut,
    K8sAlarmMonitorGroupUpdate,
    K8sAlarmMonitorServiceOut,
    K8sAlarmMonitorServiceUpdate,
    K8sAlarmMonitorSyncOut,
    K8sClusterConfigCreate,
    K8sClusterConfigOut,
    K8sClusterConfigUpdate,
    K8sConnectOut,
    K8sPodLogOut,
    K8sProjectOut,
    K8sScaleOut,
    K8sScaleRequest,
    K8sServiceOut,
    K8sWatermarkOut,
    MqttConsoleConfigOut,
    MqttConsoleConnectOut,
    MqttConsoleConnectionCreate,
    MqttConsoleConnectionOut,
    MqttConsoleConnectionTestRequest,
    MqttConsoleConnectionUpdate,
    MqttConsoleSubscriptionsUpdate,
    OmnidbMenuUrlOut,
    OmnidbOpenOut,
    RedpandaOpenOut,
    RedisinsightOpenOut,
    EmbedSessionOut,
    MqttOpenOut,
    PublicConfigOut,
    SshwiftyOpenOut,
    RepoAccessSettingsOut,
    RepoAccessSettingsUpdate,
    ReorderRequest,
    SchemaMonitorConfigUpdate,
    SchemaMonitorOut,
    SchemaMonitorPingOut,
    SchemaMonitorPingRequest,
    SchemaResetBaselineOut,
    SchemaScanResultOut,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)
from app.connection_test_service import test_connection
from app.omnidb_service import (
    build_omnidb_login_url,
    build_omnidb_public_base,
    prepare_omnidb_menu_url,
    prepare_omnidb_open,
)
from app.embed_session_service import (
    CONSOLE_DATABASE,
    CONSOLE_KAFKA,
    CONSOLE_MQTT,
    CONSOLE_REDIS,
    CONSOLE_TERMINAL,
    close_embed_session,
    create_embed_session,
    get_active_embed_session,
    update_embed_session,
)
from app.kafka_console_service import (
    create_kafka_console_connection,
    delete_kafka_console_connection,
    get_kafka_console_connection,
    list_kafka_console_connections,
    test_kafka_console_connection,
    update_kafka_console_connection,
)
from app.k8s_alarm_monitor_service import (
    list_alarm_monitor_groups,
    list_alarm_monitor_services,
    sync_alarm_monitor_data,
    update_alarm_monitor_group,
    update_alarm_monitor_service,
)
from app.k8s_monitor_service import (
    create_k8s_cluster,
    delete_k8s_cluster,
    get_k8s_cluster,
    list_k8s_clusters,
    list_k8s_projects,
    list_k8s_services,
    read_k8s_pod_logs,
    read_k8s_service_watermarks,
    scale_k8s_workload,
    test_k8s_cluster_connection,
    update_k8s_cluster,
)
from app.mqtt_console_service import (
    create_mqtt_console_connection,
    delete_mqtt_console_connection,
    get_mqtt_console_connection,
    list_mqtt_console_connections,
    prepare_mqtt_console_connect,
    test_mqtt_console_connection,
    update_mqtt_console_connection,
    update_mqtt_console_subscriptions,
)
from app.redpanda_service import (
    build_redpanda_public_base,
    disconnect_kafka_console_redpanda,
    prepare_kafka_console_redpanda_open,
    prepare_redpanda_open,
    snapshot_redpanda_console_config,
)
from app.redisinsight_service import build_redisinsight_public_base, prepare_redisinsight_open
from app.mqtt_service import prepare_mqtt_console_config
from app.sshwifty_service import build_sshwifty_public_base, prepare_sshwifty_open
from app.config import settings
from app.services import (
    connection_environment_display,
    connection_is_database_type,
    connection_is_gitlab_type,
    connection_is_kafka_type,
    connection_is_mqtt_type,
    connection_is_redis_type,
    connection_is_terminal_type,
    connection_project_display,
    create_connection,
    create_dict_item,
    create_subscription,
    batch_delete_connections,
    backfill_missing_commit_times,
    delete_connection,
    delete_dict_item,
    get_dict_label_name,
    get_home_data,
    list_activity_logs,
    list_connections,
    list_dict_items,
    list_gitlab_subscription_trees,
    get_activity_log,
    get_or_fetch_log_diff,
    reorder_connections,
    reorder_dict_items,
    update_connection,
    update_dict_item,
    update_subscription,
)
from app.repo_access_service import get_repo_access_settings_out, update_repo_access_settings
from app.schema_monitor_service import (
    get_schema_monitor_status,
    ping_schema_monitor_for_subscription,
    reset_schema_monitor_baseline,
    scan_subscription_schema_async,
    update_schema_monitor_config,
)

from app.ping_scheduler import ping_connection_record

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/public/omnidb-menu-url", response_model=OmnidbMenuUrlOut)
def public_omnidb_menu_url(request: Request):
    host_hint = request.headers.get("host")
    public_base = build_omnidb_public_base(host_hint)
    return OmnidbMenuUrlOut(url=prepare_omnidb_menu_url(public_base=public_base))


@router.get("/public/config", response_model=PublicConfigOut)
def public_config(request: Request):
    configured = get_public_webhook_base_url()
    host_hint = request.headers.get("host")
    omnidb_public_base = build_omnidb_public_base(host_hint)
    return PublicConfigOut(
        webhook_base_url=configured,
        omnidb_base_url=omnidb_public_base,
        omnidb_login_url=build_omnidb_login_url(public_base=omnidb_public_base),
        sshwifty_base_url=build_sshwifty_public_base(host_hint),
        redpanda_base_url=build_redpanda_public_base(host_hint),
        redisinsight_base_url=build_redisinsight_public_base(host_hint),
    )


@router.get("/settings/repo-access", response_model=RepoAccessSettingsOut)
def get_repo_access_settings(db: Session = Depends(get_db)):
    return get_repo_access_settings_out(db)


@router.put("/settings/repo-access", response_model=RepoAccessSettingsOut)
def put_repo_access_settings(data: RepoAccessSettingsUpdate, db: Session = Depends(get_db)):
    return update_repo_access_settings(db, data)


def _subscription_to_out(sub: Subscription, db: Session) -> SubscriptionOut:
    from app.repo_service import parse_repo_url

    conn = sub.connection
    out = SubscriptionOut.model_validate(sub)
    out.webhook_url = f"/webhooks/database?secret={sub.webhook_secret}"
    if conn:
        parsed = parse_repo_url(conn.url)
        out.connection_name = conn.name
        out.connection_url = conn.url.strip()
        out.projects = conn.projects or []
        out.environments = conn.environments or []
        out.connection_type_name = get_dict_label_name(db, conn.type)
        out.project_display = connection_project_display(db, conn)
        out.environment_display = connection_environment_display(db, conn)
        out.provider = parsed.provider
        out.github_repo = parsed.repo_path
        out.github_branch = parsed.branch
        out.repo_base_url = parsed.base_url
        out.repo_web_url = parsed.web_url or conn.url.strip()
        out.branch_display = parsed.branch or "全部分支"
    else:
        out.branch_display = out.github_branch or "全部分支"
        out.repo_web_url = out.connection_url
    return out


@router.get("/dict", response_model=list[DictItemOut])
def get_dict_items(
    type: str | None = Query(None, alias="type"),
    db: Session = Depends(get_db),
):
    items = list_dict_items(db, dict_type=type)
    return [DictItemOut.from_orm_item(item) for item in items]


@router.post("/dict", response_model=DictItemOut, status_code=201)
def post_dict_item(data: DictItemCreate, db: Session = Depends(get_db)):
    item = create_dict_item(db, data)
    return DictItemOut.from_orm_item(item)


@router.patch("/dict/reorder")
def patch_dict_reorder(data: ReorderRequest, db: Session = Depends(get_db)):
    reorder_dict_items(db, [item.model_dump() for item in data.items])
    return {"ok": True, "scope": data.scope}


@router.patch("/dict/{item_id}", response_model=DictItemOut)
def patch_dict_item(item_id: int, data: DictItemUpdate, db: Session = Depends(get_db)):
    item = db.query(DictItem).filter(DictItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Dict item not found")
    item = update_dict_item(db, item, data)
    return DictItemOut.from_orm_item(item)


@router.delete("/dict/{item_id}", status_code=204)
def remove_dict_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(DictItem).filter(DictItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Dict item not found")
    delete_dict_item(db, item)


@router.get("/connections", response_model=list[ConnectionOut])
def get_connections(
    name: str | None = Query(None),
    project: int | None = Query(None),
    environment: int | None = Query(None),
    is_shared: bool | None = Query(None),
    group_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    return [
        ConnectionOut.from_connection(conn)
        for conn in list_connections(
            db,
            name=name,
            project=project,
            environment=environment,
            is_shared=is_shared,
            group_id=group_id,
        )
    ]


@router.get("/connections/home", response_model=HomeResponse)
def get_home_connections(
    project: int = Query(...),
    environment: int = Query(...),
    db: Session = Depends(get_db),
):
    data = get_home_data(db, project, environment)
    return HomeResponse(
        groups=[
            {
                "id": group["id"],
                "name": group["name"],
                "description": group["description"],
                "sort_order": group["sort_order"],
                "is_system": group["is_system"],
                "is_project_group": group["is_project_group"],
                "connections": [
                    ConnectionOut.from_connection(conn) for conn in group["connections"]
                ],
            }
            for group in data["groups"]
        ],
        projects=[DictItemOut.from_orm_item(item) for item in data["projects"]],
        environments=[DictItemOut.from_orm_item(item) for item in data["environments"]],
        labels=[DictItemOut.from_orm_item(item) for item in data["labels"]],
        connection_groups=[DictItemOut.from_orm_item(item) for item in data["connection_groups"]],
    )


@router.post("/connections", response_model=ConnectionOut, status_code=201)
def post_connection(data: ConnectionCreate, db: Session = Depends(get_db)):
    return ConnectionOut.from_connection(create_connection(db, data))


@router.post("/connections/test-connection", response_model=ConnectionTestOut)
def post_test_connection(data: ConnectionTestRequest, db: Session = Depends(get_db)):
    return test_connection(db, data)


@router.get("/embed-sessions/{session_id}", response_model=EmbedSessionOut)
def get_embed_session(session_id: str, db: Session = Depends(get_db)):
    session = get_active_embed_session(db, session_id)
    conn = session.connection
    return EmbedSessionOut(
        session_id=session.id,
        console_type=session.console_type,
        connection_id=session.connection_id,
        connection_name=conn.name if conn else "",
        embed_url=session.embed_url or "",
        is_temporary=session.is_temporary,
    )


@router.delete("/embed-sessions/{session_id}", status_code=204)
def delete_embed_session(session_id: str, db: Session = Depends(get_db)):
    close_embed_session(db, session_id)


@router.post("/connections/{connection_id}/omnidb-open", response_model=OmnidbOpenOut)
def post_omnidb_open(
    connection_id: int,
    request: Request,
    public_host: str | None = Query(None),
    db: Session = Depends(get_db),
):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not connection_is_database_type(db, conn):
        raise HTTPException(status_code=400, detail="仅数据库类型连接支持 OmniDB")
    host_hint = public_host or request.headers.get("host")
    public_base = build_omnidb_public_base(host_hint)
    if not settings.omnidb_internal_url:
        raise HTTPException(status_code=503, detail="OmniDB 未配置")
    session = create_embed_session(db, conn, CONSOLE_DATABASE, temporary=True)
    payload = prepare_omnidb_open(
        conn,
        public_base=public_base,
        external_alias=session.external_alias,
        ensure_tab=True,
    )
    update_embed_session(
        db,
        session,
        external_id=str(payload.get("omnidb_connection_id") or ""),
        embed_url=payload["embed_url"],
    )
    payload["session_id"] = session.id
    return OmnidbOpenOut(**payload)


@router.post("/connections/{connection_id}/sshwifty-open", response_model=SshwiftyOpenOut)
def post_sshwifty_open(
    connection_id: int,
    request: Request,
    public_host: str | None = Query(None),
    db: Session = Depends(get_db),
):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not connection_is_terminal_type(db, conn):
        raise HTTPException(status_code=400, detail="仅终端模拟器类型连接支持 Sshwifty")
    host_hint = public_host or request.headers.get("host")
    public_base = build_sshwifty_public_base(host_hint)
    session = create_embed_session(db, conn, CONSOLE_TERMINAL, temporary=True)
    payload = prepare_sshwifty_open(conn, public_base=public_base)
    update_embed_session(db, session, embed_url=payload["embed_url"])
    payload["session_id"] = session.id
    return SshwiftyOpenOut(**payload)


@router.post("/connections/{connection_id}/redpanda-connect", response_model=RedpandaOpenOut)
def post_redpanda_connect(
    connection_id: int,
    request: Request,
    public_host: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """菜单入口：持久化同步集群配置，不创建临时会话。"""
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not connection_is_kafka_type(db, conn):
        raise HTTPException(status_code=400, detail="仅 Kafka 类型连接支持 Redpanda Console")
    host_hint = public_host or request.headers.get("host")
    public_base = build_redpanda_public_base(host_hint)
    if not settings.redpanda_config_path:
        raise HTTPException(status_code=503, detail="Redpanda Console 未配置")
    payload = prepare_redpanda_open(db, conn, public_base=public_base)
    return RedpandaOpenOut(**payload)


@router.get("/k8s/clusters", response_model=list[K8sClusterConfigOut])
def get_k8s_clusters(db: Session = Depends(get_db)):
    return list_k8s_clusters(db)


@router.post("/k8s/clusters", response_model=K8sClusterConfigOut, status_code=201)
def post_k8s_cluster(data: K8sClusterConfigCreate, db: Session = Depends(get_db)):
    return create_k8s_cluster(db, data)


@router.put("/k8s/clusters/{cluster_id}", response_model=K8sClusterConfigOut)
def put_k8s_cluster(
    cluster_id: int,
    data: K8sClusterConfigUpdate,
    db: Session = Depends(get_db),
):
    cluster = get_k8s_cluster(db, cluster_id)
    return update_k8s_cluster(db, cluster, data)


@router.delete("/k8s/clusters/{cluster_id}", status_code=204)
def delete_k8s_cluster_route(cluster_id: int, db: Session = Depends(get_db)):
    cluster = get_k8s_cluster(db, cluster_id)
    delete_k8s_cluster(db, cluster)


@router.post("/k8s/clusters/{cluster_id}/connect", response_model=K8sConnectOut)
def post_k8s_cluster_connect(cluster_id: int, db: Session = Depends(get_db)):
    cluster = get_k8s_cluster(db, cluster_id)
    return test_k8s_cluster_connection(db, cluster)


@router.get("/k8s/clusters/{cluster_id}/projects", response_model=list[K8sProjectOut])
def get_k8s_cluster_projects(cluster_id: int, db: Session = Depends(get_db)):
    cluster = get_k8s_cluster(db, cluster_id)
    return list_k8s_projects(cluster)


@router.get("/k8s/clusters/{cluster_id}/services", response_model=list[K8sServiceOut])
def get_k8s_cluster_services(
    cluster_id: int,
    project: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    cluster = get_k8s_cluster(db, cluster_id)
    return list_k8s_services(cluster, project)


@router.post("/k8s/clusters/{cluster_id}/scale", response_model=K8sScaleOut)
def post_k8s_cluster_scale(
    cluster_id: int,
    data: K8sScaleRequest,
    db: Session = Depends(get_db),
):
    cluster = get_k8s_cluster(db, cluster_id)
    return scale_k8s_workload(cluster, data)


@router.get("/k8s/clusters/{cluster_id}/watermarks", response_model=K8sWatermarkOut)
def get_k8s_service_watermarks(
    cluster_id: int,
    namespace: str = Query(..., min_length=1),
    service_name: str = Query(..., min_length=1),
    port: int = Query(..., ge=1, le=65535),
    db: Session = Depends(get_db),
):
    cluster = get_k8s_cluster(db, cluster_id)
    return read_k8s_service_watermarks(
        cluster,
        namespace=namespace,
        service_name=service_name,
        port=port,
    )


@router.get("/k8s/clusters/{cluster_id}/logs", response_model=K8sPodLogOut)
def get_k8s_pod_logs(
    cluster_id: int,
    namespace: str = Query(..., min_length=1),
    pod_name: str = Query(..., min_length=1),
    container: str | None = Query(None),
    tail_lines: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    cluster = get_k8s_cluster(db, cluster_id)
    return read_k8s_pod_logs(
        cluster,
        namespace=namespace,
        pod_name=pod_name,
        container=container,
        tail_lines=tail_lines,
    )


@router.post(
    "/k8s/clusters/{cluster_id}/alarm-monitor/sync",
    response_model=K8sAlarmMonitorSyncOut,
)
def post_k8s_alarm_monitor_sync(cluster_id: int, db: Session = Depends(get_db)):
    cluster = get_k8s_cluster(db, cluster_id)
    return sync_alarm_monitor_data(db, cluster)


@router.get(
    "/k8s/clusters/{cluster_id}/alarm-monitor/groups",
    response_model=list[K8sAlarmMonitorGroupOut],
)
def get_k8s_alarm_monitor_groups(cluster_id: int, db: Session = Depends(get_db)):
    cluster = get_k8s_cluster(db, cluster_id)
    return list_alarm_monitor_groups(db, cluster)


@router.put(
    "/k8s/clusters/{cluster_id}/alarm-monitor/groups/{namespace}",
    response_model=K8sAlarmMonitorGroupOut,
)
def put_k8s_alarm_monitor_group(
    cluster_id: int,
    namespace: str,
    data: K8sAlarmMonitorGroupUpdate,
    db: Session = Depends(get_db),
):
    cluster = get_k8s_cluster(db, cluster_id)
    return update_alarm_monitor_group(db, cluster, namespace, data)


@router.post(
    "/k8s/clusters/{cluster_id}/alarm-monitor/groups/{namespace}/sync",
    response_model=K8sAlarmMonitorSyncOut,
)
def post_k8s_alarm_monitor_group_sync(
    cluster_id: int,
    namespace: str,
    db: Session = Depends(get_db),
):
    cluster = get_k8s_cluster(db, cluster_id)
    return sync_alarm_monitor_data(db, cluster, namespace=namespace)


@router.get(
    "/k8s/clusters/{cluster_id}/alarm-monitor/groups/{namespace}/services",
    response_model=list[K8sAlarmMonitorServiceOut],
)
def get_k8s_alarm_monitor_services(
    cluster_id: int,
    namespace: str,
    db: Session = Depends(get_db),
):
    cluster = get_k8s_cluster(db, cluster_id)
    return list_alarm_monitor_services(db, cluster, namespace)


@router.put(
    "/k8s/clusters/{cluster_id}/alarm-monitor/groups/{namespace}/services/{service_name}",
    response_model=K8sAlarmMonitorServiceOut,
)
def put_k8s_alarm_monitor_service(
    cluster_id: int,
    namespace: str,
    service_name: str,
    data: K8sAlarmMonitorServiceUpdate,
    db: Session = Depends(get_db),
):
    cluster = get_k8s_cluster(db, cluster_id)
    return update_alarm_monitor_service(db, cluster, namespace, service_name, data)


@router.get("/kafka-console/connections", response_model=list[KafkaConsoleConnectionOut])
def get_kafka_console_connections(db: Session = Depends(get_db)):
    return list_kafka_console_connections(db)


@router.post("/kafka-console/connections", response_model=KafkaConsoleConnectionOut, status_code=201)
def post_kafka_console_connection(data: KafkaConsoleConnectionCreate, db: Session = Depends(get_db)):
    return create_kafka_console_connection(db, data)


@router.put("/kafka-console/connections/{connection_id}", response_model=KafkaConsoleConnectionOut)
def put_kafka_console_connection(
    connection_id: int,
    data: KafkaConsoleConnectionUpdate,
    db: Session = Depends(get_db),
):
    conn = get_kafka_console_connection(db, connection_id)
    return update_kafka_console_connection(db, conn, data)


@router.delete("/kafka-console/connections/{connection_id}", status_code=204)
def delete_kafka_console_connection_route(connection_id: int, db: Session = Depends(get_db)):
    conn = get_kafka_console_connection(db, connection_id)
    delete_kafka_console_connection(db, conn)


@router.post("/kafka-console/connections/test", response_model=ConnectionTestOut)
def post_kafka_console_connection_test(data: KafkaConsoleConnectionTestRequest):
    return test_kafka_console_connection(data)


@router.post("/kafka-console/connections/{connection_id}/connect", response_model=RedpandaOpenOut)
def post_kafka_console_connect(
    connection_id: int,
    request: Request,
    public_host: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """连接方式 → Kafka：同步集群配置并返回 Redpanda Console 地址。"""
    conn = get_kafka_console_connection(db, connection_id)
    host_hint = public_host or request.headers.get("host")
    public_base = build_redpanda_public_base(host_hint)
    if not settings.redpanda_config_path:
        raise HTTPException(status_code=503, detail="Redpanda Console 未配置")
    payload = prepare_kafka_console_redpanda_open(db, conn, public_base=public_base)
    return RedpandaOpenOut(**payload)


@router.post("/kafka-console/disconnect", status_code=204)
def post_kafka_console_disconnect():
    """连接方式 → Kafka：取消连接并恢复 Redpanda Console 配置。"""
    disconnect_kafka_console_redpanda()


@router.get("/mqtt-console/connections", response_model=list[MqttConsoleConnectionOut])
def get_mqtt_console_connections(db: Session = Depends(get_db)):
    return list_mqtt_console_connections(db)


@router.post("/mqtt-console/connections", response_model=MqttConsoleConnectionOut, status_code=201)
def post_mqtt_console_connection(data: MqttConsoleConnectionCreate, db: Session = Depends(get_db)):
    return create_mqtt_console_connection(db, data)


@router.put("/mqtt-console/connections/{connection_id}", response_model=MqttConsoleConnectionOut)
def put_mqtt_console_connection(
    connection_id: int,
    data: MqttConsoleConnectionUpdate,
    db: Session = Depends(get_db),
):
    conn = get_mqtt_console_connection(db, connection_id)
    return update_mqtt_console_connection(db, conn, data)


@router.delete("/mqtt-console/connections/{connection_id}", status_code=204)
def delete_mqtt_console_connection_route(connection_id: int, db: Session = Depends(get_db)):
    conn = get_mqtt_console_connection(db, connection_id)
    delete_mqtt_console_connection(db, conn)


@router.post("/mqtt-console/connections/test", response_model=ConnectionTestOut)
def post_mqtt_console_connection_test(data: MqttConsoleConnectionTestRequest):
    return test_mqtt_console_connection(data)


@router.put(
    "/mqtt-console/connections/{connection_id}/subscriptions",
    response_model=MqttConsoleConnectionOut,
)
def put_mqtt_console_subscriptions(
    connection_id: int,
    data: MqttConsoleSubscriptionsUpdate,
    db: Session = Depends(get_db),
):
    conn = get_mqtt_console_connection(db, connection_id)
    return update_mqtt_console_subscriptions(db, conn, data)


@router.post("/mqtt-console/connections/{connection_id}/connect", response_model=MqttConsoleConnectOut)
def post_mqtt_console_connect(connection_id: int, db: Session = Depends(get_db)):
    """连接方式 → MQTT：返回控制台连接参数（含密码，仅用于建立连接）。"""
    conn = get_mqtt_console_connection(db, connection_id)
    return prepare_mqtt_console_connect(conn)


@router.post("/connections/{connection_id}/redpanda-open", response_model=RedpandaOpenOut)
def post_redpanda_open(
    connection_id: int,
    request: Request,
    public_host: str | None = Query(None),
    db: Session = Depends(get_db),
):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not connection_is_kafka_type(db, conn):
        raise HTTPException(status_code=400, detail="仅 Kafka 类型连接支持 Redpanda Console")
    host_hint = public_host or request.headers.get("host")
    public_base = build_redpanda_public_base(host_hint)
    if not settings.redpanda_config_path:
        raise HTTPException(status_code=503, detail="Redpanda Console 未配置")
    session = create_embed_session(db, conn, CONSOLE_KAFKA, temporary=True)
    snapshot_before = snapshot_redpanda_console_config()
    payload = prepare_redpanda_open(
        db,
        conn,
        public_base=public_base,
        snapshot_before=snapshot_before,
    )
    update_embed_session(
        db,
        session,
        embed_url=payload["embed_url"],
        snapshot_config=snapshot_before,
    )
    payload["session_id"] = session.id
    return RedpandaOpenOut(**payload)


@router.post("/connections/{connection_id}/redisinsight-open", response_model=RedisinsightOpenOut)
def post_redisinsight_open(
    connection_id: int,
    request: Request,
    public_host: str | None = Query(None),
    db: Session = Depends(get_db),
):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not connection_is_redis_type(db, conn):
        raise HTTPException(status_code=400, detail="仅 Redis 类型连接支持 RedisInsight")
    host_hint = public_host or request.headers.get("host")
    public_base = build_redisinsight_public_base(host_hint)
    if not settings.redisinsight_internal_url:
        raise HTTPException(status_code=503, detail="RedisInsight 未配置")
    session = create_embed_session(db, conn, CONSOLE_REDIS, temporary=True)
    payload = prepare_redisinsight_open(
        conn,
        public_base=public_base,
        external_name=session.external_alias,
    )
    update_embed_session(
        db,
        session,
        external_id=str(payload.get("database_id") or ""),
        embed_url=payload["embed_url"],
    )
    payload["session_id"] = session.id
    return RedisinsightOpenOut(**payload)


@router.post("/connections/{connection_id}/mqtt-open", response_model=MqttOpenOut)
def post_mqtt_open(connection_id: int, db: Session = Depends(get_db)):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not connection_is_mqtt_type(db, conn):
        raise HTTPException(status_code=400, detail="仅 MQTT 类型连接支持控制台")
    session = create_embed_session(db, conn, CONSOLE_MQTT, temporary=True)
    config = prepare_mqtt_console_config(db, conn)
    update_embed_session(db, session, embed_url=f"/mqtt?connectionId={conn.id}&sessionId={session.id}")
    return MqttOpenOut(**config, session_id=session.id)


@router.get("/connections/{connection_id}/mqtt-config", response_model=MqttConsoleConfigOut)
def get_mqtt_config(connection_id: int, db: Session = Depends(get_db)):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return MqttConsoleConfigOut(**prepare_mqtt_console_config(db, conn))


@router.patch("/connections/reorder")
def patch_reorder(data: ReorderRequest, db: Session = Depends(get_db)):
    reorder_connections(db, [item.model_dump() for item in data.items])
    return {"ok": True, "scope": data.scope}


@router.post("/connections/batch-delete")
def post_batch_delete_connections(data: BatchDeleteRequest, db: Session = Depends(get_db)):
    deleted = batch_delete_connections(db, data.ids)
    return {"ok": True, "deleted": deleted}


@router.post("/connections/{connection_id}/ping", response_model=ConnectionOut)
async def post_connection_ping(
    connection_id: int,
    sub_index: int | None = Query(None, ge=0),
):
    connection = await ping_connection_record(connection_id, sub_index=sub_index)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection or sub-link not found")
    return ConnectionOut.from_connection(connection)


@router.get("/connections/{connection_id}", response_model=ConnectionOut)
def get_connection(connection_id: int, db: Session = Depends(get_db)):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return ConnectionOut.from_connection(conn)


@router.patch("/connections/{connection_id}", response_model=ConnectionOut)
def patch_connection(
    connection_id: int, data: ConnectionUpdate, db: Session = Depends(get_db)
):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return ConnectionOut.from_connection(update_connection(db, conn, data))


@router.delete("/connections/{connection_id}", status_code=204)
def remove_connection(connection_id: int, db: Session = Depends(get_db)):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    delete_connection(db, conn)


@router.get("/subscriptions", response_model=list[GitlabSubscriptionTreeOut])
def get_subscriptions(
    project: int | None = Query(None),
    enabled: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    return list_gitlab_subscription_trees(db, project=project, enabled=enabled)


@router.patch("/subscriptions/{subscription_id}", response_model=GitlabSubscriptionTreeOut)
async def patch_subscription(
    subscription_id: int, data: SubscriptionUpdate, db: Session = Depends(get_db)
):
    from app.api_monitor_service import resolve_link_target, schedule_api_monitor_sync

    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    old_enabled = dict(sub.link_enabled or {})
    update_subscription(db, sub, data)
    db.refresh(sub)
    conn = sub.connection
    if conn and connection_is_gitlab_type(db, conn):
        new_enabled = dict(sub.link_enabled or {})
        for link_key, enabled in new_enabled.items():
            if enabled and not old_enabled.get(link_key):
                target = resolve_link_target(conn, link_key)
                if target and str(target.get("clone_url") or "").strip():
                    schedule_api_monitor_sync(sub.id, link_key, baseline_only=True)
    trees = list_gitlab_subscription_trees(db)
    for tree in trees:
        if tree["id"] == subscription_id:
            return tree
    conn = sub.connection
    return {
        "id": sub.id,
        "connection_id": sub.connection_id,
        "connection_name": conn.name if conn else str(sub.connection_id),
        "connection_type_name": get_dict_label_name(db, conn.type) if conn else None,
        "project_display": connection_project_display(db, conn) if conn else "-",
        "environment_display": connection_environment_display(db, conn) if conn else "-",
        "links": [],
    }


@router.get("/subscriptions/{subscription_id}/schema-monitor", response_model=SchemaMonitorOut)
def get_subscription_schema_monitor(subscription_id: int, db: Session = Depends(get_db)):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        return get_schema_monitor_status(db, sub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/subscriptions/{subscription_id}/schema-monitor", response_model=SchemaMonitorOut)
def put_subscription_schema_monitor(
    subscription_id: int,
    data: SchemaMonitorConfigUpdate,
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        return update_schema_monitor_config(db, sub, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/subscriptions/{subscription_id}/schema-ping", response_model=SchemaMonitorPingOut)
def post_subscription_schema_ping(
    subscription_id: int,
    data: SchemaMonitorPingRequest | None = None,
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        return ping_schema_monitor_for_subscription(db, sub, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/subscriptions/{subscription_id}/schema-scan", response_model=SchemaScanResultOut)
async def post_subscription_schema_scan(subscription_id: int, db: Session = Depends(get_db)):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        result = await scan_subscription_schema_async(db, sub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"结构巡检失败: {exc}") from exc

    if result.get("was_first_scan"):
        message = "已完成基线快照，后续巡检将自动检测结构变更"
    elif result["changes_detected"] == 0:
        message = "巡检完成，未检测到结构变更"
    else:
        message = f"检测到 {result['changes_detected']} 项结构变更，已写入活动日志"
    snapshot = result.get("snapshot")
    if isinstance(snapshot, dict):
        snapshot_data = snapshot.get("snapshot")
    else:
        snapshot_data = snapshot.snapshot if snapshot else None
    return SchemaScanResultOut(
        subscription_id=result["subscription_id"],
        changes_detected=result["changes_detected"],
        logs_created=result["logs_created"],
        has_baseline=bool(snapshot_data),
        message=message,
    )


@router.post(
    "/subscriptions/{subscription_id}/schema-reset-baseline",
    response_model=SchemaResetBaselineOut,
)
async def post_subscription_schema_reset_baseline(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        result = await reset_schema_monitor_baseline(db, sub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"重置结构基准失败: {exc}") from exc
    return SchemaResetBaselineOut(**result)


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
def post_subscription(data: SubscriptionCreate, db: Session = Depends(get_db)):
    conn = db.query(Connection).filter(Connection.id == data.connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if conn.subscription:
        raise HTTPException(status_code=400, detail="Subscription already exists")
    sub = create_subscription(db, data)
    return _subscription_to_out(sub, db)


@router.get("/logs", response_model=list[ActivityLogOut])
async def get_logs(
    project: int | None = Query(None),
    environment: int | None = Query(None),
    source_type: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    logs = list_activity_logs(
        db, project=project, environment=environment, source_type=source_type, limit=limit
    )
    await backfill_missing_commit_times(db, logs)
    return logs


@router.get("/logs/{log_id}/diff", response_model=ActivityLogDiffOut)
async def get_log_diff(log_id: int, db: Session = Depends(get_db)):
    log = get_activity_log(db, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    data = await get_or_fetch_log_diff(db, log)
    return ActivityLogDiffOut(**data)


@router.patch("/logs/{log_id}/read", response_model=ActivityLogOut)
def mark_log_read(log_id: int, db: Session = Depends(get_db)):
    from app.models import ActivityLog

    log = db.query(ActivityLog).filter(ActivityLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    log.is_read = True
    db.commit()
    db.refresh(log)
    return log


@router.get("/api-monitor/filter-options", response_model=ApiMonitorFilterOptionsOut)
def get_api_monitor_filter_options(
    project: int | None = Query(None),
    environment: int | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.api_monitor_service import list_api_monitor_filter_options

    return list_api_monitor_filter_options(db, project=project, environment=environment)


@router.get("/api-monitor/services", response_model=list[ApiMonitorServiceOut])
def get_api_monitor_services(
    project: int | None = Query(None),
    environment: int | None = Query(None),
    name: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.api_monitor_service import list_api_monitor_services

    return list_api_monitor_services(db, project=project, environment=environment, name=name)


@router.get("/api-monitor/services/{service_id}/modules", response_model=ApiMonitorModulesOut)
def get_api_monitor_modules(service_id: str, db: Session = Depends(get_db)):
    from app.api_monitor_service import list_api_monitor_modules

    try:
        return ApiMonitorModulesOut(**list_api_monitor_modules(db, service_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api-monitor/services/{service_id}/spec", response_model=ApiMonitorSpecOut)
def get_api_monitor_spec(
    service_id: str,
    module: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.api_monitor_service import get_api_monitor_spec as load_api_monitor_spec

    try:
        return ApiMonitorSpecOut(**load_api_monitor_spec(db, service_id, module=module))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api-monitor/services/{service_id}/groups", response_model=ApiMonitorGroupsOut)
def get_api_monitor_groups(
    service_id: str,
    module: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.api_monitor_service import get_api_monitor_groups

    try:
        return ApiMonitorGroupsOut(**get_api_monitor_groups(db, service_id, module=module))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api-monitor/services/{service_id}/groups/{tag}/endpoints",
    response_model=ApiMonitorGroupEndpointsOut,
)
def get_api_monitor_group_endpoints(
    service_id: str,
    tag: str,
    module: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.api_monitor_service import get_api_monitor_group_endpoints

    try:
        return ApiMonitorGroupEndpointsOut(
            **get_api_monitor_group_endpoints(db, service_id, tag, module=module)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api-monitor/services/{service_id}/endpoints/{endpoint_id:path}/changes",
    response_model=list[ApiMonitorEndpointChangeOut],
)
def get_api_monitor_endpoint_changes(
    service_id: str,
    endpoint_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    from app.api_monitor_service import list_api_monitor_endpoint_changes

    try:
        return list_api_monitor_endpoint_changes(db, service_id, endpoint_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api-monitor/services/{service_id}/endpoints/{endpoint_id:path}", response_model=ApiMonitorEndpointOut)
def get_api_monitor_endpoint(service_id: str, endpoint_id: str, db: Session = Depends(get_db)):
    from app.api_monitor_service import get_api_monitor_endpoint as load_api_monitor_endpoint

    try:
        return ApiMonitorEndpointOut(**load_api_monitor_endpoint(db, service_id, endpoint_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api-monitor/services/{service_id}/scan-runs", response_model=list[ApiMonitorScanRunOut])
def get_api_monitor_scan_runs(
    service_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    from app.api_monitor_service import list_api_monitor_scan_runs

    try:
        return list_api_monitor_scan_runs(db, service_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api-monitor/services/{service_id}/scan-runs/{scan_run_id}/changes",
    response_model=ApiMonitorScanRunChangesOut,
)
def get_api_monitor_scan_run_changes(service_id: str, scan_run_id: int, db: Session = Depends(get_db)):
    from app.api_monitor_service import list_api_monitor_scan_run_changes

    try:
        return ApiMonitorScanRunChangesOut(**list_api_monitor_scan_run_changes(db, service_id, scan_run_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api-monitor/proxy", response_model=ApiMonitorProxyOut)
async def post_api_monitor_proxy(payload: ApiMonitorProxyIn):
    from app.api_monitor_service import proxy_api_monitor_request

    try:
        return ApiMonitorProxyOut(
            **await proxy_api_monitor_request(
                method=payload.method,
                url=payload.url,
                headers=payload.headers,
                body=payload.body,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/subscriptions/{subscription_id}/api-sync",
    response_model=ApiMonitorSyncResultOut,
)
async def sync_subscription_api(
    subscription_id: int,
    link_key: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.api_monitor_service import sync_subscription_api_links

    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        result = await sync_subscription_api_links(db, sub, link_key=link_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiMonitorSyncResultOut(
        subscription_id=subscription_id,
        synced=result["synced"],
        skipped=result.get("skipped", 0),
        failed=result.get("failed", 0),
        message=result["message"],
    )


@router.get("/api-test-cases", response_model=ApiTestCaseListOut)
def list_api_test_cases(
    project_id: int | None = Query(None),
    environment_id: int | None = Query(None),
    service: str | None = Query(None),
    endpoint_id: str | None = Query(None),
    keyword: str | None = Query(None),
    status: str = Query("active"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    from app.api_test_case_service import list_api_test_cases as load_api_test_cases

    try:
        return ApiTestCaseListOut(**load_api_test_cases(
            db,
            project_id=project_id,
            environment_id=environment_id,
            service=service,
            endpoint_id=endpoint_id,
            keyword=keyword,
            status=status,
            page=page,
            page_size=page_size,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api-test-cases/{case_id}", response_model=ApiTestCaseOut)
def get_api_test_case(case_id: int, db: Session = Depends(get_db)):
    from app.api_test_case_service import get_api_test_case as load_api_test_case

    try:
        return ApiTestCaseOut(**load_api_test_case(db, case_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api-test-cases", response_model=ApiTestCaseOut, status_code=201)
def create_api_test_case(payload: ApiTestCaseCreate, db: Session = Depends(get_db)):
    from app.api_test_case_service import create_api_test_case as save_api_test_case

    try:
        return ApiTestCaseOut(**save_api_test_case(db, payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api-test-cases/{case_id}", response_model=ApiTestCaseOut)
def update_api_test_case(case_id: int, payload: ApiTestCaseUpdate, db: Session = Depends(get_db)):
    from app.api_test_case_service import update_api_test_case as save_api_test_case

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="无更新内容")
    try:
        return ApiTestCaseOut(**save_api_test_case(db, case_id, data))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api-test-cases/batch-delete", response_model=ApiTestCaseBatchDeleteOut)
def batch_delete_api_test_cases(payload: BatchDeleteRequest, db: Session = Depends(get_db)):
    from app.api_test_case_service import batch_delete_api_test_cases as remove_api_test_cases

    try:
        return ApiTestCaseBatchDeleteOut(**remove_api_test_cases(db, payload.ids))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api-test-cases/{case_id}", status_code=204)
def delete_api_test_case(case_id: int, db: Session = Depends(get_db)):
    from app.api_test_case_service import soft_delete_api_test_case

    try:
        soft_delete_api_test_case(db, case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api-test-cases/{case_id}/permanent", status_code=204)
def permanent_delete_api_test_case(case_id: int, db: Session = Depends(get_db)):
    from app.api_test_case_service import hard_delete_api_test_case

    try:
        hard_delete_api_test_case(db, case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api-test-cases/generate-from-endpoint", response_model=ApiTestCaseGenerateOut)
async def generate_api_test_cases(payload: ApiTestCaseGenerateIn, db: Session = Depends(get_db)):
    from app.api_test_case_service import generate_api_test_cases_from_endpoint

    try:
        result = await generate_api_test_cases_from_endpoint(db, payload.model_dump())
        return ApiTestCaseGenerateOut(
            items=[ApiTestCaseOut(**item) for item in result["items"]],
            created=result.get("created", 0),
            overwritten=result.get("overwritten", 0),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api-test-cases/{case_id}/execution-result", response_model=ApiTestCaseOut)
def save_api_test_case_execution_result(
    case_id: int,
    payload: ApiTestCaseExecutionResultIn,
    db: Session = Depends(get_db),
):
    from app.api_test_case_service import save_api_test_case_execution_result as persist_execution_result

    try:
        return ApiTestCaseOut(**persist_execution_result(db, case_id, payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api-test-cases/{case_id}/restore", response_model=ApiTestCaseOut)
def restore_api_test_case(case_id: int, db: Session = Depends(get_db)):
    from app.api_test_case_service import restore_api_test_case as restore_case

    try:
        return ApiTestCaseOut(**restore_case(db, case_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/llm-configs", response_model=list[LlmConfigOut])
def list_llm_configs_api(db: Session = Depends(get_db)):
    from app.llm_config_service import list_llm_configs

    return [LlmConfigOut(**item) for item in list_llm_configs(db)]


@router.post("/llm-configs", response_model=LlmConfigOut, status_code=201)
def create_llm_config_api(payload: LlmConfigCreate, db: Session = Depends(get_db)):
    from app.llm_config_service import create_llm_config

    return LlmConfigOut(**create_llm_config(db, payload.model_dump()))


@router.put("/llm-configs/{config_id}", response_model=LlmConfigOut)
def update_llm_config_api(config_id: str, payload: LlmConfigUpdate, db: Session = Depends(get_db)):
    from app.llm_config_service import update_llm_config

    return LlmConfigOut(**update_llm_config(db, config_id, payload.model_dump()))


@router.post("/llm-configs/{config_id}/toggle", response_model=LlmConfigOut)
def toggle_llm_config_api(config_id: str, payload: LlmToggleIn, db: Session = Depends(get_db)):
    from app.llm_config_service import toggle_llm_config

    return LlmConfigOut(**toggle_llm_config(db, config_id, payload.enabled))


@router.delete("/llm-configs/{config_id}", status_code=204)
def delete_llm_config_api(config_id: str, db: Session = Depends(get_db)):
    from app.llm_config_service import delete_llm_config

    delete_llm_config(db, config_id)


@router.post("/llm-configs/test-connection", response_model=LlmConnectionTestOut)
async def test_llm_connection_api(payload: LlmConnectionTestIn, db: Session = Depends(get_db)):
    from app.llm_config_service import test_llm_connection

    return LlmConnectionTestOut(**await test_llm_connection(db, payload.model_dump()))


@router.post("/llm-configs/models", response_model=LlmModelsOut)
async def fetch_llm_models_api(payload: LlmModelsFetchIn, db: Session = Depends(get_db)):
    from app.llm_config_service import fetch_llm_models

    return LlmModelsOut(**await fetch_llm_models(db, payload.model_dump()))


@router.post("/ai-analysis", response_model=AiAnalysisOut)
async def post_ai_analysis(payload: AiAnalysisIn, db: Session = Depends(get_db)):
    from app.ai_analysis_service import run_ai_analysis

    try:
        return AiAnalysisOut(**await run_ai_analysis(db, payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/prompts", response_model=list[PromptTemplateOut])
def list_prompts_api(db: Session = Depends(get_db)):
    from app.prompt_template_service import list_prompt_templates

    return [PromptTemplateOut(**item) for item in list_prompt_templates(db)]


@router.post("/prompts", response_model=PromptTemplateOut, status_code=201)
def create_prompt_api(payload: PromptTemplateIn, db: Session = Depends(get_db)):
    from app.prompt_template_service import create_prompt_template

    return PromptTemplateOut(**create_prompt_template(db, payload.model_dump()))


@router.put("/prompts/{prompt_id}", response_model=PromptTemplateOut)
def update_prompt_api(prompt_id: str, payload: PromptTemplateIn, db: Session = Depends(get_db)):
    from app.prompt_template_service import update_prompt_template

    return PromptTemplateOut(**update_prompt_template(db, prompt_id, payload.model_dump()))


@router.post("/prompts/{prompt_id}/toggle", response_model=PromptTemplateOut)
def toggle_prompt_api(prompt_id: str, payload: LlmToggleIn, db: Session = Depends(get_db)):
    from app.prompt_template_service import toggle_prompt_template

    return PromptTemplateOut(**toggle_prompt_template(db, prompt_id, payload.enabled))


@router.delete("/prompts/{prompt_id}", status_code=204)
def delete_prompt_api(prompt_id: str, db: Session = Depends(get_db)):
    from app.prompt_template_service import delete_prompt_template

    delete_prompt_template(db, prompt_id)

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.database import get_db
from app.repo_access_config import get_public_webhook_base_url
from app.models import Connection, DictItem, Subscription
from app.schemas import (
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
def patch_subscription(
    subscription_id: int, data: SubscriptionUpdate, db: Session = Depends(get_db)
):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    update_subscription(db, sub, data)
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

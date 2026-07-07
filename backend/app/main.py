import asyncio
import logging
import time
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.models import Connection, DictItem, EmbedConsoleSession
from app.mqtt_bridge_service import run_mqtt_bridge, run_mqtt_bridge_session
from app.k8s_alarm_scheduler import k8s_alarm_scheduler
from app.ping_scheduler import connection_ping_scheduler
from app.schema_monitor_scheduler import schema_monitor_scheduler
from app.routers import api, webhooks
from app.services import (
    DICT_CONNECTION_GROUP,
    DICT_ENVIRONMENT,
    DICT_LABEL,
    DICT_PROJECT,
    LABEL_DATABASE,
    LABEL_OTHER,
    LABEL_KAFKA,
    LABEL_K8S,
    LABEL_MQTT,
    LABEL_REDIS,
    LABEL_TERMINAL,
    PROJECT_CONNECTION_GROUP_NAME,
    connection_is_mqtt_type,
)
from app.k8s_exec_service import run_k8s_exec_bridge
from app.k8s_monitor_service import get_k8s_cluster
from app.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


def _warn_default_webhook_secrets() -> None:
    if settings.github_webhook_secret.strip() in ("", "change-me-github-secret"):
        logger.warning(
            "GITHUB_WEBHOOK_SECRET 仍为默认值，GitHub webhook 将被拒绝。请在 .env 中配置非默认密钥。"
        )
    if settings.gitlab_webhook_secret.strip() in ("", "change-me-gitlab-secret"):
        logger.warning(
            "GITLAB_WEBHOOK_SECRET 仍为默认值，GitLab webhook 将被拒绝。请在 .env 中配置非默认密钥。"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _warn_default_webhook_secrets()
    ping_task = asyncio.create_task(connection_ping_scheduler())
    schema_task = asyncio.create_task(schema_monitor_scheduler())
    k8s_alarm_task = asyncio.create_task(k8s_alarm_scheduler())
    yield
    for task in (ping_task, schema_task, k8s_alarm_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="QuickNavigation API", version="1.0.0", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)
app.include_router(webhooks.router)


def wait_for_db(max_retries: int = 30, delay: float = 2.0) -> None:
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception:
            if i == max_retries - 1:
                raise
            time.sleep(delay)


def migrate_drop_dict_name_unique() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("dict_items"):
        return
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE dict_items DROP INDEX uq_dict_type_name"))
        except Exception:
            pass


def seed_dict_items(db) -> None:
    if db.query(DictItem).count() > 0:
        return
    seeds = [
        (DICT_PROJECT, "默认项目", "系统默认项目", 0),
        (DICT_PROJECT, "订单服务", "订单微服务项目", 1),
        (DICT_ENVIRONMENT, "开发环境", None, 0),
        (DICT_ENVIRONMENT, "测试环境", None, 1),
        (DICT_ENVIRONMENT, "预发环境", None, 2),
        (DICT_ENVIRONMENT, "生产环境", None, 3),
        (DICT_LABEL, LABEL_OTHER, "普通跳转连接", 0, True),
        (DICT_LABEL, "GitHub 仓库", "GitHub 代码仓库", 1, False),
        (DICT_LABEL, "GitLab 仓库", "GitLab 代码仓库", 2, True),
        (DICT_LABEL, LABEL_DATABASE, "数据库连接", 3, True),
        (DICT_LABEL, LABEL_TERMINAL, "SSH/终端模拟器连接", 4, True),
        (DICT_LABEL, LABEL_REDIS, "Redis 缓存连接", 5, True),
        (DICT_LABEL, LABEL_MQTT, "MQTT 消息连接", 6, True),
        (DICT_LABEL, LABEL_KAFKA, "Kafka 消息队列连接", 7, True),
        (DICT_LABEL, LABEL_K8S, "Kubernetes 集群连接", 8, True),
    ]
    db.add_all(
        [
            DictItem(
                dict_type=dict_type,
                name=name,
                description=desc,
                sort_order=sort_order,
                is_system=is_system,
            )
            for dict_type, name, desc, sort_order, is_system in seeds
        ]
    )
    db.commit()


def migrate_connection_multi_select() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    if "projects" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE connections ADD COLUMN projects JSON NULL"))
        conn.execute(text("ALTER TABLE connections ADD COLUMN environments JSON NULL"))
        if "project" in cols:
            conn.execute(
                text(
                    "UPDATE connections SET projects = JSON_ARRAY(project) "
                    "WHERE project IS NOT NULL AND project != ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE connections SET environments = JSON_ARRAY(environment) "
                    "WHERE environment IS NOT NULL AND environment != ''"
                )
            )
        conn.execute(text("UPDATE connections SET projects = JSON_ARRAY() WHERE projects IS NULL"))
        conn.execute(
            text("UPDATE connections SET environments = JSON_ARRAY() WHERE environments IS NULL")
        )


def migrate_connection_reachability() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    with engine.begin() as conn:
        if "is_reachable" not in cols:
            conn.execute(text("ALTER TABLE connections ADD COLUMN is_reachable BOOLEAN NULL"))
        if "last_checked_at" not in cols:
            conn.execute(text("ALTER TABLE connections ADD COLUMN last_checked_at DATETIME NULL"))


def migrate_connection_data_fix() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    with engine.begin() as conn:
        if "projects" in cols:
            conn.execute(text("UPDATE connections SET projects = JSON_ARRAY() WHERE projects IS NULL"))
            if "project" in cols:
                conn.execute(
                    text(
                        "UPDATE connections SET projects = JSON_ARRAY(project) "
                        "WHERE (projects IS NULL OR JSON_LENGTH(projects) = 0) "
                        "AND project IS NOT NULL AND project != ''"
                    )
                )
        if "environments" in cols:
            conn.execute(
                text("UPDATE connections SET environments = JSON_ARRAY() WHERE environments IS NULL")
            )
            if "environment" in cols:
                conn.execute(
                    text(
                        "UPDATE connections SET environments = JSON_ARRAY(environment) "
                        "WHERE (environments IS NULL OR JSON_LENGTH(environments) = 0) "
                        "AND environment IS NOT NULL AND environment != ''"
                    )
                )


def migrate_drop_legacy_connection_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    with engine.begin() as conn:
        if "project" in cols and "projects" in cols:
            conn.execute(text("ALTER TABLE connections DROP COLUMN project"))
        if "environment" in cols and "environments" in cols:
            conn.execute(text("ALTER TABLE connections DROP COLUMN environment"))


def migrate_connection_type_column() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    for column in inspector.get_columns("connections"):
        if column["name"] == "type" and "enum" in str(column["type"]).lower():
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE connections MODIFY COLUMN type VARCHAR(64) "
                        "NOT NULL DEFAULT 'normal'"
                    )
                )
            break


def migrate_connection_sub_links() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    if "sub_links" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE connections ADD COLUMN sub_links JSON NULL")
        )
        conn.execute(text("UPDATE connections SET sub_links = JSON_ARRAY() WHERE sub_links IS NULL"))


def migrate_connection_dict_ids() -> None:
    import json as json_lib

    inspector = inspect(engine)
    if not inspector.has_table("connections") or not inspector.has_table("dict_items"):
        return

    db = SessionLocal()
    try:
        items = db.query(DictItem).all()
        name_maps: dict[str, dict[str, int]] = {
            DICT_PROJECT: {},
            DICT_ENVIRONMENT: {},
            DICT_LABEL: {},
        }
        for item in items:
            name_maps.setdefault(item.dict_type, {})[item.name] = item.id

        rows = db.execute(text("SELECT id, projects, environments, type FROM connections")).fetchall()
        for row_id, projects_raw, environments_raw, conn_type in rows:
            projects_data = projects_raw
            environments_data = environments_raw
            if isinstance(projects_data, str):
                projects_data = json_lib.loads(projects_data)
            if isinstance(environments_data, str):
                environments_data = json_lib.loads(environments_data)

            new_projects: list[int] = []
            for value in projects_data or []:
                if isinstance(value, int):
                    new_projects.append(value)
                elif isinstance(value, str):
                    mapped = name_maps.get(DICT_PROJECT, {}).get(value)
                    if mapped is not None:
                        new_projects.append(mapped)

            new_environments: list[int] = []
            for value in environments_data or []:
                if isinstance(value, int):
                    new_environments.append(value)
                elif isinstance(value, str):
                    mapped = name_maps.get(DICT_ENVIRONMENT, {}).get(value)
                    if mapped is not None:
                        new_environments.append(mapped)

            if isinstance(conn_type, str) and not conn_type.isdigit():
                new_type = name_maps.get(DICT_LABEL, {}).get(conn_type)
                if new_type is None:
                    new_type = name_maps.get(DICT_LABEL, {}).get("normal", 1)
            else:
                new_type = int(conn_type)

            db.execute(
                text(
                    "UPDATE connections SET projects = :projects, environments = :environments, "
                    "type = :type WHERE id = :id"
                ),
                {
                    "id": row_id,
                    "projects": json_lib.dumps(new_projects),
                    "environments": json_lib.dumps(new_environments),
                    "type": new_type,
                },
            )
        db.commit()
    finally:
        db.close()

    type_column = next(
        (column for column in inspector.get_columns("connections") if column["name"] == "type"),
        None,
    )
    if type_column and "int" not in str(type_column["type"]).lower():
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE connections MODIFY COLUMN type INT NOT NULL DEFAULT 1"))


def _dict_id(db, dict_type: str, name: str) -> int:
    item = (
        db.query(DictItem)
        .filter(DictItem.dict_type == dict_type, DictItem.name == name)
        .first()
    )
    if not item:
        raise RuntimeError(f"Missing dict seed: {dict_type}/{name}")
    return item.id


def seed_connections(db) -> None:
    if db.query(Connection).count() > 0:
        return
    normal = _dict_id(db, DICT_LABEL, "普通连接")
    database = _dict_id(db, DICT_LABEL, "数据库")
    github = _dict_id(db, DICT_LABEL, "GitHub 仓库")
    order_service = _dict_id(db, DICT_PROJECT, "订单服务")
    test_env = _dict_id(db, DICT_ENVIRONMENT, "测试环境")
    dev_env = _dict_id(db, DICT_ENVIRONMENT, "开发环境")
    project_group = (
        db.query(DictItem)
        .filter(
            DictItem.dict_type == DICT_CONNECTION_GROUP,
            DictItem.is_system.is_(True),
        )
        .first()
    )
    shared_group = (
        db.query(DictItem)
        .filter(
            DictItem.dict_type == DICT_CONNECTION_GROUP,
            DictItem.name == "共用连接",
        )
        .first()
    )
    if not project_group or not shared_group:
        return
    seed = [
        Connection(
            name="团队 Wiki",
            url="https://wiki.example.com",
            description="内部文档",
            projects=[],
            environments=[],
            type=normal,
            group_id=shared_group.id,
            is_shared=True,
            sort_order=0,
        ),
        Connection(
            name="监控大盘",
            url="https://grafana.example.com",
            description="Grafana 监控",
            projects=[],
            environments=[],
            type=normal,
            group_id=shared_group.id,
            is_shared=True,
            sort_order=1,
        ),
        Connection(
            name="测试 API",
            url="https://api-test.example.com",
            description="测试环境接口",
            projects=[order_service],
            environments=[test_env],
            type=normal,
            group_id=project_group.id,
            is_shared=False,
            sort_order=0,
        ),
        Connection(
            name="测试数据库",
            url="https://db-admin.example.com",
            description="MySQL 管理",
            projects=[order_service],
            environments=[test_env],
            type=database,
            group_id=project_group.id,
            is_shared=False,
            sort_order=1,
        ),
        Connection(
            name="GitHub 仓库",
            url="https://github.com/org/order-service",
            description="代码仓库",
            projects=[order_service],
            environments=[test_env, dev_env],
            type=github,
            group_id=project_group.id,
            is_shared=False,
            sort_order=2,
        ),
    ]
    db.add_all(seed)
    db.commit()


def migrate_subscription_github_branch() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("subscriptions"):
        return
    cols = {column["name"] for column in inspector.get_columns("subscriptions")}
    if "github_branch" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE subscriptions ADD COLUMN github_branch VARCHAR(128) NULL"))


def migrate_connection_endpoint_fields() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    additions = {
        "host": "VARCHAR(256) NULL",
        "port": "INT NULL",
        "username": "VARCHAR(128) NULL",
        "password": "VARCHAR(512) NULL",
        "database_name": "VARCHAR(128) NULL",
    }
    with engine.begin() as conn:
        for column_name, column_type in additions.items():
            if column_name not in cols:
                conn.execute(text(f"ALTER TABLE connections ADD COLUMN {column_name} {column_type}"))


def migrate_embed_console_sessions() -> None:
    inspector = inspect(engine)
    if inspector.has_table("embed_console_sessions"):
        return
    Base.metadata.tables["embed_console_sessions"].create(bind=engine)


def migrate_kafka_console_connections() -> None:
    inspector = inspect(engine)
    if inspector.has_table("kafka_console_connections"):
        return
    Base.metadata.tables["kafka_console_connections"].create(bind=engine)


def migrate_mqtt_console_connections() -> None:
    inspector = inspect(engine)
    if inspector.has_table("mqtt_console_connections"):
        return
    Base.metadata.tables["mqtt_console_connections"].create(bind=engine)


def migrate_mqtt_console_subscriptions() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("mqtt_console_connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("mqtt_console_connections")}
    if "mqtt_subscriptions" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE mqtt_console_connections ADD COLUMN mqtt_subscriptions JSON NULL")
        )
        conn.execute(
            text(
                "UPDATE mqtt_console_connections SET mqtt_subscriptions = JSON_ARRAY() "
                "WHERE mqtt_subscriptions IS NULL"
            )
        )


def migrate_mqtt_fields() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    with engine.begin() as conn:
        if "mqtt_ws_path" not in cols:
            conn.execute(text("ALTER TABLE connections ADD COLUMN mqtt_ws_path VARCHAR(128) NULL"))
        if "mqtt_subscriptions" not in cols:
            conn.execute(text("ALTER TABLE connections ADD COLUMN mqtt_subscriptions JSON NULL"))
            conn.execute(text("UPDATE connections SET mqtt_subscriptions = JSON_ARRAY() WHERE mqtt_subscriptions IS NULL"))


def seed_system_labels(db) -> None:
    legacy_normal = (
        db.query(DictItem)
        .filter(DictItem.dict_type == DICT_LABEL, DictItem.name == "普通连接")
        .first()
    )
    if legacy_normal:
        legacy_normal.name = LABEL_OTHER
        legacy_normal.description = legacy_normal.description or "普通跳转连接"
        legacy_normal.is_system = True

    system_labels = [
        (LABEL_OTHER, "普通跳转连接", 0),
        (LABEL_DATABASE, "数据库连接", 3),
        (LABEL_TERMINAL, "SSH/终端模拟器连接", 4),
        (LABEL_REDIS, "Redis 缓存连接", 5),
        (LABEL_MQTT, "MQTT 消息连接", 6),
        (LABEL_KAFKA, "Kafka 消息队列连接", 7),
        (LABEL_K8S, "Kubernetes 集群连接", 8),
    ]
    for name, description, sort_order in system_labels:
        item = (
            db.query(DictItem)
            .filter(DictItem.dict_type == DICT_LABEL, DictItem.name == name)
            .first()
        )
        if item:
            item.is_system = True
            item.description = item.description or description
            item.sort_order = sort_order
            continue
        db.add(
            DictItem(
                dict_type=DICT_LABEL,
                name=name,
                description=description,
                sort_order=sort_order,
                is_system=True,
            )
        )
    db.commit()


def seed_gitlab_label(db) -> None:
    exists = (
        db.query(DictItem)
        .filter(DictItem.dict_type == DICT_LABEL, DictItem.name == "GitLab 仓库")
        .first()
    )
    if exists:
        if not exists.is_system:
            exists.is_system = True
            db.commit()
        return
    db.add(
        DictItem(
            dict_type=DICT_LABEL,
            name="GitLab 仓库",
            description="GitLab 代码仓库",
            sort_order=3,
            is_system=True,
        )
    )
    db.commit()


def migrate_subscription_link_enabled() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("subscriptions"):
        return
    cols = {column["name"] for column in inspector.get_columns("subscriptions")}
    with engine.begin() as conn:
        if "link_enabled" not in cols:
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN link_enabled JSON NULL"))
        conn.execute(
            text("UPDATE subscriptions SET link_enabled = CAST('{}' AS JSON) WHERE link_enabled IS NULL")
        )


def migrate_dict_is_system() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("dict_items"):
        return
    cols = {column["name"] for column in inspector.get_columns("dict_items")}
    if "is_system" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE dict_items ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT 0"))


def migrate_connection_group_id() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    if "group_id" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE connections ADD COLUMN group_id INT NULL"))
        conn.execute(text("CREATE INDEX ix_connections_group_id ON connections (group_id)"))


def seed_connection_groups(db) -> None:
    project_group = (
        db.query(DictItem)
        .filter(
            DictItem.dict_type == DICT_CONNECTION_GROUP,
            DictItem.is_system.is_(True),
        )
        .first()
    )
    if not project_group:
        project_group = DictItem(
            dict_type=DICT_CONNECTION_GROUP,
            name=PROJECT_CONNECTION_GROUP_NAME,
            description="按项目与环境筛选的连接",
            sort_order=0,
            is_system=True,
        )
        db.add(project_group)
        db.flush()

    shared_group = (
        db.query(DictItem)
        .filter(
            DictItem.dict_type == DICT_CONNECTION_GROUP,
            DictItem.name == "共用连接",
        )
        .first()
    )
    if not shared_group:
        shared_group = DictItem(
            dict_type=DICT_CONNECTION_GROUP,
            name="共用连接",
            description="所有项目环境可见",
            sort_order=1,
            is_system=False,
        )
        db.add(shared_group)
        db.flush()

    db.commit()
    db.refresh(project_group)
    db.refresh(shared_group)

    connections = db.query(Connection).all()
    changed = False
    for conn in connections:
        if conn.group_id:
            continue
        if conn.is_shared:
            conn.group_id = shared_group.id
        else:
            conn.group_id = project_group.id
        changed = True
    if changed:
        db.commit()


def migrate_api_test_case_response_assert() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("api_test_cases"):
        return
    cols = {column["name"] for column in inspector.get_columns("api_test_cases")}
    with engine.begin() as conn:
        if "response_assert_mode" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE api_test_cases ADD COLUMN response_assert_mode "
                    "VARCHAR(16) NOT NULL DEFAULT 'text'"
                )
            )
        if "response_assert_rules" not in cols:
            conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN response_assert_rules TEXT NULL"))


def migrate_api_test_case_execution_result() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("api_test_cases"):
        return
    cols = {column["name"] for column in inspector.get_columns("api_test_cases")}
    with engine.begin() as conn:
        if "last_exec_pass" not in cols:
            conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN last_exec_pass BOOLEAN NULL"))
        if "last_exec_status_code" not in cols:
            conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN last_exec_status_code INT NULL"))
        if "last_exec_response" not in cols:
            conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN last_exec_response TEXT NULL"))
        if "last_exec_detail" not in cols:
            conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN last_exec_detail TEXT NULL"))
        if "last_exec_at" not in cols:
            conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN last_exec_at DATETIME NULL"))


def migrate_api_test_case_request_headers() -> None:
    import json

    from app.models import ApiTestCase

    inspector = inspect(engine)
    if not inspector.has_table("api_test_cases"):
        return
    cols = {column["name"] for column in inspector.get_columns("api_test_cases")}
    with engine.begin() as conn:
        if "request_headers" not in cols:
            conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN request_headers TEXT NULL"))

    db = SessionLocal()
    try:
        changed = False
        for case in db.query(ApiTestCase).all():
            if case.request_headers:
                continue
            raw = (case.request_params or "").strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict) or "headers" not in parsed:
                continue
            headers = parsed.get("headers")
            if not isinstance(headers, dict):
                continue
            case.request_headers = json.dumps(headers, ensure_ascii=False, indent=2)
            parsed.pop("headers", None)
            case.request_params = (
                json.dumps(parsed, ensure_ascii=False, indent=2) if parsed else None
            )
            changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def migrate_k8s_alarm_pod_restart_snapshot() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("k8s_alarm_monitor_snapshots"):
        return
    cols = {column["name"] for column in inspector.get_columns("k8s_alarm_monitor_snapshots")}
    if "pod_restart_snapshot" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE k8s_alarm_monitor_snapshots ADD COLUMN pod_restart_snapshot JSON NULL")
        )


def migrate_k8s_alarm_exception_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("k8s_alarm_monitor_snapshots"):
        return
    cols = {column["name"] for column in inspector.get_columns("k8s_alarm_monitor_snapshots")}
    with engine.begin() as conn:
        if "last_exception_timestamp" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE k8s_alarm_monitor_snapshots ADD COLUMN last_exception_timestamp INT NULL"
                )
            )
        if "exception_alert_active" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE k8s_alarm_monitor_snapshots ADD COLUMN exception_alert_active BOOLEAN NOT NULL DEFAULT 0"
                )
            )


def migrate_repo_access_ssh_key() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("repo_access_settings"):
        return
    cols = {column["name"] for column in inspector.get_columns("repo_access_settings")}
    if "gitlab_ssh_private_key" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE repo_access_settings ADD COLUMN gitlab_ssh_private_key TEXT NULL")
        )
        conn.execute(
            text("UPDATE repo_access_settings SET gitlab_ssh_private_key = '' WHERE gitlab_ssh_private_key IS NULL")
        )


def migrate_k8s_cluster_connection_id() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("k8s_cluster_configs"):
        return
    cols = {column["name"] for column in inspector.get_columns("k8s_cluster_configs")}
    if "connection_id" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE k8s_cluster_configs ADD COLUMN connection_id INT NULL"))
        conn.execute(
            text(
                "ALTER TABLE k8s_cluster_configs "
                "ADD UNIQUE INDEX uq_k8s_cluster_connection_id (connection_id)"
            )
        )


def migrate_k8s_cluster_name() -> None:
    """Kuboard provider 需要额外存储 Kuboard 内部的集群标识（如 slimsys）。"""
    inspector = inspect(engine)
    if not inspector.has_table("k8s_cluster_configs"):
        return
    cols = {column["name"] for column in inspector.get_columns("k8s_cluster_configs")}
    if "cluster_name" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE k8s_cluster_configs ADD COLUMN cluster_name VARCHAR(128) NULL"))


def init_db() -> None:
    wait_for_db()
    Base.metadata.create_all(bind=engine)
    migrate_dict_is_system()
    migrate_connection_group_id()
    migrate_connection_multi_select()
    migrate_connection_reachability()
    migrate_connection_data_fix()
    migrate_drop_legacy_connection_columns()
    migrate_connection_type_column()
    migrate_connection_sub_links()
    migrate_connection_dict_ids()
    migrate_drop_dict_name_unique()
    migrate_subscription_github_branch()
    migrate_subscription_link_enabled()
    migrate_connection_endpoint_fields()
    migrate_mqtt_fields()
    migrate_embed_console_sessions()
    migrate_kafka_console_connections()
    migrate_mqtt_console_connections()
    migrate_mqtt_console_subscriptions()
    migrate_api_test_case_response_assert()
    migrate_api_test_case_execution_result()
    migrate_api_test_case_request_headers()
    migrate_k8s_alarm_pod_restart_snapshot()
    migrate_k8s_alarm_exception_columns()
    migrate_k8s_cluster_connection_id()
    migrate_k8s_cluster_name()
    migrate_repo_access_ssh_key()
    db = SessionLocal()
    try:
        seed_dict_items(db)
        seed_system_labels(db)
        seed_gitlab_label(db)
        seed_connection_groups(db)
        seed_connections(db)
        from app.llm_config_service import seed_llm_configs
        from app.prompt_template_service import seed_prompt_templates

        seed_llm_configs(db)
        seed_prompt_templates(db)
        from app.prompt_template_service import sync_api_case_generate_prompt

        sync_api_case_generate_prompt(db)
        from app.prompt_template_service import ensure_general_ai_analysis_prompt

        ensure_general_ai_analysis_prompt(db)
        from app.prompt_template_service import ensure_code_interpretation_prompt

        ensure_code_interpretation_prompt(db)
        from app.repo_access_service import sync_repo_access_cache_from_db

        sync_repo_access_cache_from_db(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)


@app.websocket("/ws/mqtt/manual")
async def websocket_mqtt_manual_bridge(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
    except TimeoutError:
        await websocket.send_json(
            {"type": "status", "status": "error", "message": "等待连接参数超时"}
        )
        return
    except Exception:
        await websocket.send_json(
            {"type": "status", "status": "error", "message": "连接参数无效"}
        )
        return

    if data.get("type") != "connect":
        await websocket.send_json(
            {"type": "status", "status": "error", "message": "首条消息须为 connect"}
        )
        return

    host = str(data.get("host") or "").strip()
    if not host:
        await websocket.send_json({"type": "status", "status": "error", "message": "未配置主机"})
        return

    port = int(data.get("port") or 1883)
    username = str(data.get("username") or "").strip() or None
    password = str(data.get("password") or "").strip() or None

    await run_mqtt_bridge_session(
        websocket,
        hostname=host,
        port=port,
        username=username,
        password=password,
        preset_topics=[],
        bridge_id="manual",
        accept_websocket=False,
    )


@app.websocket("/ws/k8s/clusters/{cluster_id}/exec")
async def websocket_k8s_exec(websocket: WebSocket, cluster_id: int):
    await websocket.accept()
    namespace = (websocket.query_params.get("namespace") or "").strip()
    pod_name = (websocket.query_params.get("pod_name") or "").strip()
    container = (websocket.query_params.get("container") or "").strip() or None
    db = SessionLocal()
    try:
        try:
            cluster = get_k8s_cluster(db, cluster_id)
        except HTTPException as exc:
            await websocket.send_json(
                {"type": "status", "status": "error", "message": str(exc.detail)},
            )
            await websocket.close(code=4404)
            return
        await run_k8s_exec_bridge(
            websocket,
            cluster,
            namespace=namespace,
            pod_name=pod_name,
            container=container,
        )
    except Exception as exc:
        logger.exception("k8s exec websocket failed")
        try:
            await websocket.send_json(
                {"type": "status", "status": "error", "message": f"终端连接失败：{exc}"},
            )
        except Exception:
            pass
    finally:
        db.close()


@app.websocket("/ws/mqtt/{connection_id}")
async def websocket_mqtt_bridge(websocket: WebSocket, connection_id: int):
    db = SessionLocal()
    try:
        conn = db.query(Connection).filter(Connection.id == connection_id).first()
        if not conn:
            await websocket.close(code=4404)
            return
        if not connection_is_mqtt_type(db, conn):
            await websocket.close(code=4403)
            return
        preset_topics: list[str] = []
        for item in conn.mqtt_subscriptions or []:
            if isinstance(item, dict):
                topic = str(item.get("topic", "")).strip()
                if topic:
                    preset_topics.append(topic)
        await run_mqtt_bridge(websocket, conn, preset_topics)
    finally:
        db.close()

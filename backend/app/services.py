import json

import secrets

from datetime import datetime, timezone

from typing import Any



from fastapi import HTTPException

from sqlalchemy import func, or_

from sqlalchemy.orm import Session, joinedload



from app.models import ActivityLog, Connection, DictItem, Subscription

from app.schemas import (

    ConnectionCreate,

    ConnectionUpdate,

    DatabaseWebhookPayload,

    DictItemCreate,

    DictItemUpdate,

    SubscriptionCreate,

    SubscriptionUpdate,

)



DICT_PROJECT = "project"

DICT_ENVIRONMENT = "environment"

DICT_LABEL = "label"

DICT_CONNECTION_GROUP = "connection_group"

PROJECT_CONNECTION_GROUP_NAME = "项目连接"

LABEL_OTHER = "其他"
LABEL_DATABASE = "数据库"
LABEL_TERMINAL = "终端模拟器"
LABEL_REDIS = "Redis"
LABEL_MQTT = "MQTT"
LABEL_KAFKA = "Kafka"
LABEL_K8S = "K8s"
LABEL_GITLAB = "GitLab 仓库"
SYSTEM_LABEL_NAMES = {
    LABEL_OTHER,
    LABEL_DATABASE,
    LABEL_TERMINAL,
    LABEL_REDIS,
    LABEL_MQTT,
    LABEL_KAFKA,
    LABEL_K8S,
    LABEL_GITLAB,
}

FILTER_EMPTY = 0  # 筛选「其他」：项目/环境未填写





def _json_contains(column, value: int):

    return func.json_contains(column, json.dumps(value))


def _json_is_empty(column):

    return or_(column.is_(None), func.coalesce(func.json_length(column), 0) == 0)


def _normalize_connection_payload(payload: dict[str, Any]) -> dict[str, Any]:

    data = dict(payload)

    if data.get("url") is not None:

        data["url"] = str(data["url"]).strip()

    if data.get("name") is not None:

        data["name"] = str(data["name"]).strip()

    if data.get("is_shared") and data.get("group_id") is None:

        data["projects"] = []

        data["environments"] = []

    if data.get("type") is not None:

        data["type"] = int(data["type"])

    if data.get("group_id") is not None:

        data["group_id"] = int(data["group_id"])

    for key in ("projects", "environments"):

        if key in data and data[key] is not None:

            data[key] = [int(item) for item in data[key]]

    sub_links = data.get("sub_links") or []

    cleaned: list[dict[str, Any]] = []

    for item in sub_links:

        if isinstance(item, dict):

            name = str(item.get("name", "")).strip()

            url = str(item.get("url", "")).strip()
            clone_url = _optional_clone_url(item.get("clone_url"))

            is_reachable = item.get("is_reachable")

            last_checked_at = item.get("last_checked_at")

        else:

            name = str(getattr(item, "name", "")).strip()

            url = str(getattr(item, "url", "")).strip()
            clone_url = _optional_clone_url(getattr(item, "clone_url", None))

            is_reachable = getattr(item, "is_reachable", None)

            last_checked_at = getattr(item, "last_checked_at", None)

        if name and url:

            row: dict[str, Any] = {"name": name, "url": url}
            if clone_url:
                row["clone_url"] = clone_url

            if is_reachable is not None:

                row["is_reachable"] = is_reachable

            if last_checked_at is not None:

                row["last_checked_at"] = last_checked_at

            cleaned.append(row)

    data["sub_links"] = cleaned

    mqtt_subscriptions = data.get("mqtt_subscriptions") or []
    mqtt_cleaned: list[dict[str, Any]] = []
    for item in mqtt_subscriptions:
        if isinstance(item, dict):
            topic = str(item.get("topic", "")).strip()
            name = str(item.get("name", "")).strip()
        else:
            topic = str(getattr(item, "topic", "")).strip()
            name = str(getattr(item, "name", "")).strip()
        if topic:
            mqtt_cleaned.append({"topic": topic, "name": name or topic})
    data["mqtt_subscriptions"] = mqtt_cleaned

    if "mqtt_ws_path" in data and data["mqtt_ws_path"] is not None:
        path = str(data["mqtt_ws_path"]).strip()
        data["mqtt_ws_path"] = path or "/mqtt"

    for key in ("host", "username", "database_name"):
        if key in data and data[key] is not None:
            data[key] = str(data[key]).strip() or None
    if "port" in data and data["port"] is not None:
        data["port"] = int(data["port"])
    if "password" in data and data["password"] is not None:
        password = str(data["password"]).strip()
        data["password"] = password or None

    return data


def _optional_clone_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "none", "null"}:
        return ""
    return text


def get_label_kind(db: Session, type_id: int) -> str:
    item = get_dict_item(db, type_id, DICT_LABEL)
    if not item:
        return "other"
    if item.name == LABEL_DATABASE:
        return "database"
    if item.name == LABEL_TERMINAL:
        return "terminal"
    if item.name == LABEL_REDIS:
        return "redis"
    if item.name == LABEL_MQTT:
        return "mqtt"
    if item.name == LABEL_KAFKA:
        return "kafka"
    if item.name == LABEL_K8S:
        return "k8s"
    if item.name == LABEL_GITLAB or "gitlab" in item.name.lower():
        return "gitlab"
    return "other"


def _build_connection_url(kind: str, data: dict[str, Any]) -> str:
    host = str(data.get("host") or "").strip()
    if not host:
        return str(data.get("url") or "").strip()
    port = data.get("port")
    if kind == "database":
        port = port or 3306
        database_name = str(data.get("database_name") or "").strip()
        suffix = f"/{database_name}" if database_name else ""
        return f"mysql://{host}:{port}{suffix}"
    if kind == "terminal":
        port = port or 22
        username = str(data.get("username") or "").strip()
        auth = f"{username}@" if username else ""
        return f"ssh://{auth}{host}:{port}"
    if kind == "redis":
        port = port or 6379
        return f"redis://{host}:{port}"
    if kind == "mqtt":
        port = port or 1883
        return f"mqtt://{host}:{port}"
    if kind == "kafka":
        from app.kafka_broker_utils import format_kafka_brokers

        brokers = format_kafka_brokers(host, port)
        return f"kafka://{brokers}" if brokers else ""
    if kind == "k8s":
        return str(data.get("url") or data.get("host") or "").strip()
    return str(data.get("url") or "").strip()


def _validate_connection_by_kind(kind: str, data: dict[str, Any], *, require_password: bool) -> None:
    if kind == "gitlab":
        if not str(data.get("url") or "").strip():
            raise HTTPException(status_code=400, detail="请输入仓库 URL")
        return
    if kind == "other":
        if not str(data.get("url") or "").strip():
            raise HTTPException(status_code=400, detail="请输入 URL")
        return

    if kind == "k8s":
        if not str(data.get("url") or data.get("host") or "").strip():
            raise HTTPException(status_code=400, detail="请输入集群访问地址")
        return

    if not str(data.get("host") or "").strip():
        raise HTTPException(status_code=400, detail="请输入 IP")
    if kind == "kafka":
        from app.kafka_broker_utils import validate_kafka_brokers

        try:
            validate_kafka_brokers(data.get("host"), data.get("port"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif data.get("port") is None:
        raise HTTPException(status_code=400, detail="请输入端口")

    if kind == "database":
        if not str(data.get("username") or "").strip():
            raise HTTPException(status_code=400, detail="请输入用户名")
    elif kind == "terminal":
        if not str(data.get("username") or "").strip():
            raise HTTPException(status_code=400, detail="请输入账号")
        if require_password and not str(data.get("password") or "").strip():
            raise HTTPException(status_code=400, detail="请输入密码")


def _clear_connection_fields_for_kind(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    if kind == "gitlab":
        payload["port"] = None
        payload["username"] = None
        payload["password"] = None
        payload["database_name"] = None
        payload["mqtt_subscriptions"] = []
        payload["mqtt_ws_path"] = None
        cleaned_sub_links = []
        for item in payload.get("sub_links") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            url = str(item.get("url") or "").strip()
            clone_url = _optional_clone_url(item.get("clone_url"))
            if name and url:
                cleaned_sub_links.append(
                    {
                        "name": name,
                        "url": url,
                        "clone_url": clone_url or None,
                        "is_reachable": item.get("is_reachable"),
                        "last_checked_at": item.get("last_checked_at"),
                    }
                )
        payload["sub_links"] = cleaned_sub_links
        return payload
    if kind == "k8s":
        from app.k8s_connection_service import apply_k8s_connection_fields

        payload = apply_k8s_connection_fields(payload)
        payload["username"] = str(payload.get("username") or "").strip() or None
        password = str(payload.get("password") or "").strip()
        if password:
            payload["password"] = password
        else:
            payload.pop("password", None)
        return payload
    if kind == "other":
        for key in ("host", "port", "username", "password", "database_name"):
            payload[key] = None
        return payload
    payload["url"] = _build_connection_url(kind, payload)
    payload["sub_links"] = []
    if kind != "database":
        payload["database_name"] = None
    if kind == "redis":
        payload["username"] = None
    if kind == "mqtt":
        payload["mqtt_ws_path"] = str(payload.get("mqtt_ws_path") or "/mqtt").strip() or "/mqtt"
    if kind == "kafka":
        from app.kafka_broker_utils import normalize_kafka_brokers_field

        brokers_text, _ = normalize_kafka_brokers_field(payload.get("host"), payload.get("port"))
        payload["host"] = brokers_text or None
        payload["port"] = None
        payload["username"] = str(payload.get("username") or "").strip() or None
    if kind != "mqtt":
        payload["mqtt_subscriptions"] = []
        payload["mqtt_ws_path"] = None
    return payload


def connection_to_out_dict(conn: Connection) -> dict[str, Any]:
    return {
        "id": conn.id,
        "name": conn.name,
        "url": conn.url,
        "description": conn.description,
        "projects": conn.projects or [],
        "environments": conn.environments or [],
        "type": conn.type,
        "group_id": conn.group_id,
        "is_shared": conn.is_shared,
        "sort_order": conn.sort_order,
        "icon": conn.icon,
        "sub_links": conn.sub_links or [],
        "host": conn.host,
        "port": conn.port,
        "username": conn.username,
        "database_name": conn.database_name,
        "mqtt_ws_path": conn.mqtt_ws_path,
        "mqtt_subscriptions": conn.mqtt_subscriptions or [],
        "password_set": bool(conn.password),
        "is_reachable": conn.is_reachable,
        "last_checked_at": conn.last_checked_at,
        "created_at": conn.created_at,
        "updated_at": conn.updated_at,
    }





def _build_dict_maps(db: Session) -> dict[str, dict[Any, int]]:

    items = db.query(DictItem).all()

    by_type_name: dict[str, dict[str, int]] = {

        DICT_PROJECT: {},

        DICT_ENVIRONMENT: {},

        DICT_LABEL: {},

    }

    for item in items:

        by_type_name.setdefault(item.dict_type, {})[item.name] = item.id

    return by_type_name





def get_dict_item(db: Session, item_id: int, dict_type: str | None = None) -> DictItem | None:

    query = db.query(DictItem).filter(DictItem.id == item_id)

    if dict_type:

        query = query.filter(DictItem.dict_type == dict_type)

    return query.first()





def get_dict_label_name(db: Session, item_id: int) -> str:

    item = get_dict_item(db, item_id, DICT_LABEL)

    if not item:

        return str(item_id)

    return item.name


def _primary_project_environment(db: Session, conn: Connection) -> tuple[str, str]:

    project_id = conn.projects[0] if conn.projects else None

    environment_id = conn.environments[0] if conn.environments else None

    project = str(project_id) if project_id is not None else ""

    environment = str(environment_id) if environment_id is not None else ""

    return project, environment





def list_dict_items(db: Session, dict_type: str | None = None) -> list[DictItem]:

    query = db.query(DictItem)

    if dict_type:

        query = query.filter(DictItem.dict_type == dict_type)

    return query.order_by(DictItem.sort_order.asc(), DictItem.id.asc()).all()





def get_project_connection_group(db: Session) -> DictItem | None:

    return (

        db.query(DictItem)

        .filter(

            DictItem.dict_type == DICT_CONNECTION_GROUP,

            DictItem.is_system.is_(True),

        )

        .first()

    )





def is_project_connection_group(db: Session, group_id: int | None) -> bool:

    if group_id is None:

        return False

    item = get_dict_item(db, int(group_id), DICT_CONNECTION_GROUP)

    return bool(item and item.is_system)





def apply_group_rules(db: Session, data: dict[str, Any]) -> None:

    group_id = data.get("group_id")

    if group_id is None:

        return

    group_id = int(group_id)

    _ensure_dict_id(db, DICT_CONNECTION_GROUP, group_id, "分组")

    if is_project_connection_group(db, group_id):

        data["is_shared"] = False

    else:

        data["is_shared"] = True

        data["projects"] = []

        data["environments"] = []





def _ensure_dict_id(db: Session, dict_type: str, item_id: int, field_label: str) -> None:

    exists = get_dict_item(db, item_id, dict_type)

    if not exists:

        raise HTTPException(

            status_code=400,

            detail=f"{field_label} ID {item_id} 不存在，请先在字典中配置",

        )





def _validate_connection_dict_values(db: Session, data: dict[str, Any]) -> None:

    if data.get("group_id") is not None:

        apply_group_rules(db, data)

    elif data.get("is_shared"):

        data["projects"] = []

        data["environments"] = []

        if "type" in data and data["type"] is not None:

            _ensure_dict_id(db, DICT_LABEL, int(data["type"]), "类型")

        return

    projects = data.get("projects")

    if projects is not None:
        for item_id in projects:

            _ensure_dict_id(db, DICT_PROJECT, int(item_id), "项目")

    environments = data.get("environments")

    if environments is not None:
        for item_id in environments:

            _ensure_dict_id(db, DICT_ENVIRONMENT, int(item_id), "环境")

    if "type" in data and data["type"] is not None:

        _ensure_dict_id(db, DICT_LABEL, int(data["type"]), "类型")





def _connection_uses_dict_id(db: Session, item: DictItem) -> bool:

    item_id = item.id

    for conn in db.query(Connection).all():

        if item_id in (conn.projects or []) or item_id in (conn.environments or []):

            return True

        if conn.type == item_id:

            return True

        if item.dict_type == DICT_CONNECTION_GROUP and conn.group_id == item_id:

            return True

    return False





def create_dict_item(db: Session, data: DictItemCreate) -> DictItem:

    if data.type == DICT_CONNECTION_GROUP and data.name == PROJECT_CONNECTION_GROUP_NAME:

        raise HTTPException(status_code=400, detail="「项目连接」为系统默认分组，不可重复创建")

    if data.type == DICT_LABEL and data.name in SYSTEM_LABEL_NAMES:

        raise HTTPException(status_code=400, detail=f"「{data.name}」为系统预置类型，不可重复创建")

    item = DictItem(

        dict_type=data.type,

        name=data.name,

        description=data.description,

        sort_order=data.sort_order,

    )

    db.add(item)

    db.commit()

    db.refresh(item)

    return item





def update_dict_item(db: Session, item: DictItem, data: DictItemUpdate) -> DictItem:

    payload = data.model_dump(exclude_unset=True)

    if item.is_system:

        if payload.get("name") and payload["name"] != item.name:

            raise HTTPException(status_code=400, detail="系统预置项不可修改名称")

        payload.pop("name", None)

        payload.pop("type", None)

    if "type" in payload:

        item.dict_type = payload.pop("type")

    for key, value in payload.items():

        setattr(item, key, value)

    db.commit()

    db.refresh(item)

    return item





def delete_dict_item(db: Session, item: DictItem) -> None:

    if item.is_system:

        raise HTTPException(status_code=400, detail="系统预置项不可删除")

    if _connection_uses_dict_id(db, item):

        raise HTTPException(status_code=400, detail="该字典项已被连接引用，无法删除")

    db.delete(item)

    db.commit()





def reorder_dict_items(db: Session, items: list[dict[str, int]]) -> None:

    id_map = {item["id"]: item["sort_order"] for item in items}

    dict_items = db.query(DictItem).filter(DictItem.id.in_(id_map.keys())).all()

    for row in dict_items:

        row.sort_order = id_map[row.id]

    db.commit()





def list_connections(

    db: Session,

    name: str | None = None,

    project: int | None = None,

    environment: int | None = None,

    is_shared: bool | None = None,

    group_id: int | None = None,

) -> list[Connection]:

    query = db.query(Connection)

    if name:

        query = query.filter(Connection.name.contains(name))

    if is_shared is not None:

        query = query.filter(Connection.is_shared.is_(is_shared))

    if group_id is not None:

        query = query.filter(Connection.group_id == group_id)

    if project is not None:

        if project == FILTER_EMPTY:

            query = query.filter(_json_is_empty(Connection.projects))

        else:

            query = query.filter(_json_contains(Connection.projects, project))

    if environment is not None:

        if environment == FILTER_EMPTY:

            query = query.filter(_json_is_empty(Connection.environments))

        else:

            query = query.filter(_json_contains(Connection.environments, environment))

    return query.order_by(Connection.sort_order.asc(), Connection.id.asc()).all()





def get_home_data(db: Session, project: int, environment: int) -> dict[str, Any]:

    group_items = list_dict_items(db, DICT_CONNECTION_GROUP)

    groups: list[dict[str, Any]] = []

    for group in group_items:

        if group.is_system:

            connections = (

                db.query(Connection)

                .filter(

                    Connection.group_id == group.id,

                    _json_contains(Connection.projects, project),

                    _json_contains(Connection.environments, environment),

                )

                .order_by(Connection.sort_order.asc(), Connection.id.asc())

                .all()

            )

        else:

            connections = (

                db.query(Connection)

                .filter(Connection.group_id == group.id)

                .order_by(Connection.sort_order.asc(), Connection.id.asc())

                .all()

            )

        groups.append(

            {

                "id": group.id,

                "name": group.name,

                "description": group.description,

                "sort_order": group.sort_order,

                "is_system": group.is_system,

                "is_project_group": group.is_system,

                "connections": connections,

            }

        )

    return {

        "groups": groups,

        "projects": list_dict_items(db, DICT_PROJECT),

        "environments": list_dict_items(db, DICT_ENVIRONMENT),

        "labels": list_dict_items(db, DICT_LABEL),

        "connection_groups": group_items,

    }





def create_connection(db: Session, data: ConnectionCreate) -> Connection:

    payload = _normalize_connection_payload(data.model_dump())

    _validate_connection_dict_values(db, payload)

    kind = get_label_kind(db, int(payload["type"]))
    _validate_connection_by_kind(
        kind,
        payload,
        require_password=kind == "terminal",
    )
    payload = _clear_connection_fields_for_kind(kind, payload)

    conn = Connection(**payload)

    db.add(conn)

    db.commit()

    db.refresh(conn)

    ensure_gitlab_subscription(db, conn)

    ensure_database_subscription(db, conn)

    ensure_k8s_subscription(db, conn)

    from app.k8s_connection_service import sync_k8s_cluster_from_connection

    sync_k8s_cluster_from_connection(db, conn)

    return conn





def update_connection(db: Session, conn: Connection, data: ConnectionUpdate) -> Connection:

    payload = data.model_dump(exclude_unset=True)

    if "password" in payload and not str(payload.get("password") or "").strip():
        payload.pop("password", None)

    merged = {

        "group_id": payload.get("group_id", conn.group_id),

        "is_shared": payload.get("is_shared", conn.is_shared),

        "projects": payload.get("projects", conn.projects or []),

        "environments": payload.get("environments", conn.environments or []),

        "type": payload.get("type", conn.type),

        "name": payload.get("name", conn.name),

        "url": payload.get("url", conn.url),

        "host": payload.get("host", conn.host),

        "port": payload.get("port", conn.port),

        "username": payload.get("username", conn.username),

        "password": payload.get("password", conn.password),

        "database_name": payload.get("database_name", conn.database_name),

        "sub_links": payload.get("sub_links", conn.sub_links or []),

    }

    merged = _normalize_connection_payload(merged)

    _validate_connection_dict_values(db, merged)

    kind = get_label_kind(db, int(merged["type"]))
    require_password = kind == "terminal" and not conn.password
    _validate_connection_by_kind(kind, merged, require_password=require_password)
    normalized = _clear_connection_fields_for_kind(kind, merged)

    for key in ("url", "host", "port", "username", "database_name", "sub_links"):
        if key in normalized:
            payload[key] = normalized[key]
    if kind == "other":
        for key in ("host", "port", "username", "database_name"):
            payload[key] = None
        if "password" in payload or conn.password:
            payload["password"] = None
    elif "password" not in payload:
        pass
    elif kind == "redis" and "username" in payload:
        payload["username"] = None



    for key, value in payload.items():

        setattr(conn, key, value)

    conn.group_id = merged.get("group_id", conn.group_id)

    conn.is_shared = merged.get("is_shared", conn.is_shared)

    conn.projects = merged.get("projects", conn.projects or [])

    conn.environments = merged.get("environments", conn.environments or [])



    db.commit()

    db.refresh(conn)

    if "url" in payload and conn.subscription:
        refresh_subscription_from_connection(db, conn.subscription)

    ensure_gitlab_subscription(db, conn)

    ensure_database_subscription(db, conn)

    ensure_k8s_subscription(db, conn)

    from app.k8s_connection_service import sync_k8s_cluster_from_connection

    sync_k8s_cluster_from_connection(db, conn)

    return conn


def delete_connection(db: Session, conn: Connection) -> None:
    db.delete(conn)
    db.commit()


def batch_delete_connections(db: Session, ids: list[int]) -> int:

    deleted = db.query(Connection).filter(Connection.id.in_(ids)).delete(synchronize_session=False)

    db.commit()

    return deleted





def reorder_connections(db: Session, items: list[dict[str, int]]) -> None:

    id_map = {item["id"]: item["sort_order"] for item in items}

    connections = db.query(Connection).filter(Connection.id.in_(id_map.keys())).all()

    for conn in connections:

        conn.sort_order = id_map[conn.id]

    db.commit()





def _gitlab_label_ids(db: Session) -> set[int]:
    items = db.query(DictItem).filter(DictItem.dict_type == DICT_LABEL).all()
    return {item.id for item in items if "gitlab" in item.name.lower()}


def _database_label_ids(db: Session) -> set[int]:
    items = db.query(DictItem).filter(DictItem.dict_type == DICT_LABEL).all()
    return {item.id for item in items if item.name == LABEL_DATABASE}


def _k8s_label_ids(db: Session) -> set[int]:
    items = db.query(DictItem).filter(DictItem.dict_type == DICT_LABEL).all()
    return {item.id for item in items if item.name == LABEL_K8S}


def _terminal_label_ids(db: Session) -> set[int]:
    items = db.query(DictItem).filter(DictItem.dict_type == DICT_LABEL).all()
    return {item.id for item in items if item.name == LABEL_TERMINAL}


def _subscription_label_ids(db: Session) -> set[int]:
    return _gitlab_label_ids(db) | _database_label_ids(db) | _k8s_label_ids(db)


def connection_is_gitlab_type(db: Session, conn: Connection) -> bool:
    return conn.type in _gitlab_label_ids(db)


def connection_is_database_type(db: Session, conn: Connection) -> bool:
    return conn.type in _database_label_ids(db)


def connection_is_k8s_type(db: Session, conn: Connection) -> bool:
    return conn.type in _k8s_label_ids(db)


def connection_is_terminal_type(db: Session, conn: Connection) -> bool:
    return conn.type in _terminal_label_ids(db)


def _mqtt_label_ids(db: Session) -> set[int]:
    items = db.query(DictItem).filter(DictItem.dict_type == DICT_LABEL).all()
    return {item.id for item in items if item.name == LABEL_MQTT}


def connection_is_mqtt_type(db: Session, conn: Connection) -> bool:
    return conn.type in _mqtt_label_ids(db)


def _kafka_label_ids(db: Session) -> set[int]:
    items = db.query(DictItem).filter(DictItem.dict_type == DICT_LABEL).all()
    return {item.id for item in items if item.name == LABEL_KAFKA}


def connection_is_kafka_type(db: Session, conn: Connection) -> bool:
    return conn.type in _kafka_label_ids(db)


def _redis_label_ids(db: Session) -> set[int]:
    items = db.query(DictItem).filter(DictItem.dict_type == DICT_LABEL).all()
    return {item.id for item in items if item.name == LABEL_REDIS}


def connection_is_redis_type(db: Session, conn: Connection) -> bool:
    return conn.type in _redis_label_ids(db)


def _dict_ids_display(db: Session, dict_type: str, ids: list | None) -> str:
    if not ids:
        return ""
    names: list[str] = []
    for raw_id in ids:
        item = get_dict_item(db, int(raw_id), dict_type)
        names.append(item.name if item else str(raw_id))
    return "、".join(names)


def connection_project_display(db: Session, conn: Connection) -> str:
    if conn.group_id and not is_project_connection_group(db, conn.group_id):
        return "共用"
    if not conn.projects:
        return "共用"
    text = _dict_ids_display(db, DICT_PROJECT, conn.projects)
    return text or "共用"


def connection_environment_display(db: Session, conn: Connection) -> str:
    if not conn.environments:
        return "-"
    return _dict_ids_display(db, DICT_ENVIRONMENT, conn.environments) or "-"


def refresh_subscription_from_connection(db, sub) -> None:
    from app.repo_service import parse_repo_url

    conn = sub.connection
    if not conn:
        return
    parsed = parse_repo_url(conn.url)
    changed = False
    if sub.github_repo != parsed.repo_path:
        sub.github_repo = parsed.repo_path
        changed = True
    if sub.github_branch != parsed.branch:
        sub.github_branch = parsed.branch
        changed = True
    if parsed.repo_path and not sub.github_events:
        sub.github_events = ["push"]
        changed = True
    if changed:
        db.commit()
        db.refresh(sub)


def build_gitlab_subscription_links(
    conn: Connection,
    link_enabled: dict[str, bool] | None,
) -> list[dict[str, Any]]:
    from app.repo_service import parse_gitlab_tree_branch

    states = link_enabled or {}
    links: list[dict[str, Any]] = []

    main_url = conn.url.strip()
    if main_url:
        main_parsed = parse_gitlab_tree_branch(main_url)
        links.append(
            {
                "link_key": "main",
                "name": "主链接",
                "url": main_url,
                "clone_url": _optional_clone_url(conn.host),
                "branch": main_parsed.branch if main_parsed else "-",
                "repo_path": main_parsed.repo_path if main_parsed else "",
                "enabled": bool(states.get("main", False)),
                "link_kind": "gitlab",
            }
        )

    for index, item in enumerate(conn.sub_links or []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        parsed = parse_gitlab_tree_branch(url)
        if not parsed:
            continue
        key = f"sub:{index}"
        links.append(
            {
                "link_key": key,
                "name": str(item.get("name") or f"子链接 {index + 1}").strip(),
                "url": url,
                "clone_url": _optional_clone_url(item.get("clone_url")),
                "branch": parsed.branch,
                "repo_path": parsed.repo_path,
                "enabled": bool(states.get(key, False)),
                "link_kind": "gitlab",
            }
        )
    return links


def build_database_subscription_links(
    conn: Connection,
    sub: Subscription,
    link_enabled: dict[str, bool] | None,
) -> list[dict[str, Any]]:
    states = link_enabled or {}
    enabled = bool(states.get("main", sub.enabled))
    return [
        {
            "link_key": "main",
            "name": "主链接",
            "url": conn.url.strip(),
            "branch": "-",
            "repo_path": "",
            "enabled": enabled,
            "link_kind": "database",
            "webhook_secret": sub.webhook_secret,
        }
    ]


def _parse_commit_timestamp(value: str) -> datetime | None:
    text = value.strip().replace(" UTC", "Z")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _utc_iso_z(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _activity_display_time(log: ActivityLog) -> datetime:
    payload = log.payload or {}
    if log.source_type == "gitlab":
        committed = payload.get("committed_at")
        if isinstance(committed, str) and committed.strip():
            parsed = _parse_commit_timestamp(committed)
            if parsed is not None:
                return parsed
    return log.occurred_at


def _load_subscription_activity_logs(
    db: Session, connection_ids: list[int]
) -> dict[int, list[ActivityLog]]:
    if not connection_ids:
        return {}
    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.connection_id.in_(connection_ids))
        .order_by(ActivityLog.occurred_at.desc())
        .all()
    )
    grouped: dict[int, list[ActivityLog]] = {connection_id: [] for connection_id in connection_ids}
    for log in logs:
        if log.connection_id in grouped:
            grouped[log.connection_id].append(log)
    return grouped


def _last_updated_for_subscription_link(
    connection_id: int,
    link: dict[str, Any],
    logs_by_connection: dict[int, list[ActivityLog]],
) -> datetime | None:
    from app.repo_service import repos_match

    logs = logs_by_connection.get(connection_id, [])
    if not logs:
        return None

    if link.get("link_kind") == "database":
        latest: datetime | None = None
        for log in logs:
            if log.source_type != "database":
                continue
            ts = _activity_display_time(log)
            if latest is None or ts > latest:
                latest = ts
        return latest

    if link.get("link_kind") == "k8s":
        latest: datetime | None = None
        for log in logs:
            if log.source_type != "k8s":
                continue
            ts = _activity_display_time(log)
            if latest is None or ts > latest:
                latest = ts
        return latest

    repo_path = str(link.get("repo_path") or "").strip()
    branch = str(link.get("branch") or "").strip()
    if not repo_path or not branch or branch == "-":
        return None

    latest = None
    for log in logs:
        if log.source_type != "gitlab":
            continue
        payload = log.payload or {}
        repo = payload.get("repo")
        log_branch = payload.get("branch")
        if not repos_match(repo_path, str(repo) if repo is not None else None):
            continue
        if str(log_branch) != branch:
            continue
        ts = _activity_display_time(log)
        if latest is None or ts > latest:
            latest = ts
    return latest


def _attach_subscription_link_activity_times(
    db: Session,
    trees: list[dict[str, Any]],
) -> None:
    connection_ids = [int(tree["connection_id"]) for tree in trees if tree.get("connection_id")]
    logs_by_connection = _load_subscription_activity_logs(db, connection_ids)
    for tree in trees:
        conn_id = int(tree["connection_id"])
        for link in tree.get("links") or []:
            last_updated = _last_updated_for_subscription_link(conn_id, link, logs_by_connection)
            link["last_updated_at"] = _utc_iso_z(last_updated) if last_updated else None


def list_gitlab_subscription_trees(
    db: Session,
    project: int | None = None,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    sync_gitlab_subscriptions(db)
    sync_database_subscriptions(db)
    sync_k8s_subscriptions(db)
    label_ids = _subscription_label_ids(db)
    if not label_ids:
        return []

    query = db.query(Subscription).join(Connection).options(joinedload(Subscription.connection))
    query = query.filter(Connection.type.in_(label_ids))
    if project is not None:
        if project == FILTER_EMPTY:
            query = query.filter(_json_is_empty(Connection.projects))
        else:
            query = query.filter(_json_contains(Connection.projects, project))

    subs = query.order_by(Connection.sort_order.asc(), Connection.id.asc()).all()
    trees: list[dict[str, Any]] = []
    for sub in subs:
        conn = sub.connection
        if not conn:
            continue
        if connection_is_gitlab_type(db, conn):
            refresh_subscription_from_connection(db, sub)
            links = build_gitlab_subscription_links(conn, sub.link_enabled)
        elif connection_is_database_type(db, conn):
            links = build_database_subscription_links(conn, sub, sub.link_enabled)
        elif connection_is_k8s_type(db, conn):
            from app.k8s_connection_service import (
                build_k8s_subscription_links,
                get_k8s_cluster_by_connection_id,
                sync_k8s_cluster_from_connection,
            )

            cluster = get_k8s_cluster_by_connection_id(db, conn.id) or sync_k8s_cluster_from_connection(
                db, conn
            )
            links = build_k8s_subscription_links(
                conn,
                sub,
                sub.link_enabled,
                cluster_id=cluster.id if cluster else None,
            )
        else:
            continue
        if not links:
            continue
        if enabled is not None:
            links = [link for link in links if link["enabled"] is enabled]
            if not links:
                continue
        trees.append(
            {
                "id": sub.id,
                "connection_id": conn.id,
                "connection_name": conn.name,
                "connection_type_name": get_dict_label_name(db, conn.type),
                "project_display": connection_project_display(db, conn),
                "environment_display": connection_environment_display(db, conn),
                "links": links,
            }
        )
    _attach_subscription_link_activity_times(db, trees)
    _attach_api_snapshot_meta(db, trees)
    return trees


def _attach_api_snapshot_meta(db: Session, trees: list[dict[str, Any]]) -> None:
    from app.models import ApiSnapshot

    subscription_ids = [int(tree["id"]) for tree in trees if tree.get("id")]
    if not subscription_ids:
        return
    rows = db.query(ApiSnapshot).filter(ApiSnapshot.subscription_id.in_(subscription_ids)).all()
    by_sub: dict[int, dict[str, ApiSnapshot]] = {}
    for row in rows:
        by_sub.setdefault(row.subscription_id, {})[row.link_key] = row
    for tree in trees:
        snapshots = by_sub.get(int(tree["id"]), {})
        for link in tree.get("links") or []:
            snap = snapshots.get(str(link.get("link_key") or ""))
            if not snap:
                link["api_scan_status"] = None
                link["api_endpoint_count"] = 0
                continue
            link["api_scan_status"] = snap.scan_status
            link["api_endpoint_count"] = int((snap.spec or {}).get("endpoint_count") or 0) if snap.spec else 0


def iter_enabled_gitlab_links(sub: Subscription, provider: str, event: str):
    if provider != "gitlab" or not sub.connection:
        return
    if sub.github_events and event not in sub.github_events:
        return
    for link in build_gitlab_subscription_links(sub.connection, sub.link_enabled):
        if link["enabled"]:
            yield link


def match_gitlab_link(link: dict[str, Any], repo_full_name: str | None, branch: str) -> bool:
    from app.repo_service import repos_match

    if not link.get("enabled"):
        return False
    repo_path = link.get("repo_path")
    link_branch = link.get("branch")
    if not repo_path or not link_branch or link_branch == "-":
        return False
    if not repos_match(repo_path, repo_full_name):
        return False
    return str(link_branch) == branch


def ensure_database_subscription(db: Session, conn: Connection) -> Subscription | None:
    if not connection_is_database_type(db, conn):
        return conn.subscription
    if conn.subscription:
        return conn.subscription
    sub = create_subscription(
        db,
        SubscriptionCreate(connection_id=conn.id, enabled=False),
    )
    db.refresh(conn)
    return sub


def sync_database_subscriptions(db: Session) -> None:
    label_ids = _database_label_ids(db)
    if not label_ids:
        return
    connections = (
        db.query(Connection)
        .filter(Connection.type.in_(label_ids))
        .options(joinedload(Connection.subscription))
        .all()
    )
    for conn in connections:
        ensure_database_subscription(db, conn)


def ensure_k8s_subscription(db: Session, conn: Connection) -> Subscription | None:
    if not connection_is_k8s_type(db, conn):
        return conn.subscription
    if conn.subscription:
        return conn.subscription
    sub = create_subscription(
        db,
        SubscriptionCreate(connection_id=conn.id, enabled=False),
    )
    db.refresh(conn)
    return sub


def sync_k8s_subscriptions(db: Session) -> None:
    label_ids = _k8s_label_ids(db)
    if not label_ids:
        return
    connections = (
        db.query(Connection)
        .filter(Connection.type.in_(label_ids))
        .options(joinedload(Connection.subscription))
        .all()
    )
    for conn in connections:
        ensure_k8s_subscription(db, conn)
        from app.k8s_connection_service import sync_k8s_cluster_from_connection

        sync_k8s_cluster_from_connection(db, conn)


def ensure_gitlab_subscription(db: Session, conn: Connection) -> Subscription | None:
    if not connection_is_gitlab_type(db, conn):
        return conn.subscription
    if conn.subscription:
        refresh_subscription_from_connection(db, conn.subscription)
        return conn.subscription
    sub = create_subscription(
        db,
        SubscriptionCreate(connection_id=conn.id, enabled=False),
    )
    db.refresh(conn)
    return sub


def sync_gitlab_subscriptions(db: Session) -> None:
    label_ids = _gitlab_label_ids(db)
    if not label_ids:
        return
    connections = (
        db.query(Connection)
        .filter(Connection.type.in_(label_ids))
        .options(joinedload(Connection.subscription))
        .all()
    )
    for conn in connections:
        ensure_gitlab_subscription(db, conn)


def create_subscription(db: Session, data: SubscriptionCreate) -> Subscription:
    conn = db.query(Connection).filter(Connection.id == data.connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    from app.repo_service import parse_repo_url

    github_repo = data.github_repo
    github_branch = data.github_branch
    github_events = data.github_events
    parsed = parse_repo_url(conn.url)
    if parsed.repo_path:
        github_repo = github_repo or parsed.repo_path
        github_branch = github_branch if github_branch is not None else parsed.branch
        github_events = github_events or ["push"]

    sub = Subscription(
        connection_id=data.connection_id,
        enabled=data.enabled,
        github_repo=github_repo,
        github_branch=github_branch,
        github_events=github_events,
        link_enabled={},
        db_filter=data.db_filter,
        notify_homepage=data.notify_homepage,
        webhook_secret=secrets.token_hex(16),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub





def update_subscription(db: Session, sub: Subscription, data: SubscriptionUpdate) -> Subscription:
    payload = data.model_dump(exclude_unset=True)
    link_enabled = payload.pop("link_enabled", None)
    if link_enabled is not None:
        merged = dict(sub.link_enabled or {})
        merged.update({str(k): bool(v) for k, v in link_enabled.items()})
        sub.link_enabled = merged
    for key, value in payload.items():
        setattr(sub, key, value)
    db.commit()
    db.refresh(sub)
    return sub


def list_subscriptions(
    db: Session,
    project: int | None = None,
    enabled: bool | None = None,
) -> list[Subscription]:
    sync_gitlab_subscriptions(db)
    label_ids = _gitlab_label_ids(db)
    query = db.query(Subscription).join(Connection).options(joinedload(Subscription.connection))
    if label_ids:
        query = query.filter(Connection.type.in_(label_ids))
    else:
        return []
    if enabled is not None:
        query = query.filter(Subscription.enabled.is_(enabled))
    if project is not None:
        if project == FILTER_EMPTY:
            query = query.filter(_json_is_empty(Connection.projects))
        else:
            query = query.filter(_json_contains(Connection.projects, project))
    subs = query.order_by(Connection.sort_order.asc(), Connection.id.asc()).all()
    for sub in subs:
        refresh_subscription_from_connection(db, sub)
    return subs


def get_activity_log(db: Session, log_id: int) -> ActivityLog | None:
    return db.query(ActivityLog).filter(ActivityLog.id == log_id).first()


async def get_or_fetch_log_diff(db: Session, log: ActivityLog) -> dict[str, Any]:
    from app.repo_access_service import sync_repo_access_cache_from_db
    from app.repo_service import (
        build_gitlab_clone_url,
        extract_commit_sha,
        fetch_commit_diff,
        _resolve_log_clone_url,
    )

    sync_repo_access_cache_from_db(db)
    payload = dict(log.payload or {})
    commit_sha = extract_commit_sha(payload)
    repo = payload.get("repo")
    provider = str(payload.get("provider") or "github")
    base_out = {
        "log_id": log.id,
        "commit_sha": commit_sha,
        "diff": "",
        "repo": repo,
        "branch": payload.get("branch"),
        "provider": provider,
        "message": None,
    }
    if not commit_sha or not repo:
        base_out["diff"] = payload.get("diff") or ""
        return base_out

    cached = payload.get("diff")
    if isinstance(cached, str) and cached.strip():
        base_out["diff"] = cached
        return base_out

    clone_url = _resolve_log_clone_url(db, log, str(repo), provider)
    branch = str(payload.get("branch") or "").strip() or None
    result = await fetch_commit_diff(
        provider,
        str(repo),
        str(commit_sha),
        clone_url=clone_url,
        branch=branch,
        subscription_id=log.subscription_id,
    )
    base_out["diff"] = result.diff
    base_out["message"] = result.error
    if result.diff:
        payload["diff"] = result.diff
        payload.pop("diff_error", None)
        log.payload = payload
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(log, "payload")
        db.commit()
        db.refresh(log)
    elif result.error:
        payload["diff_error"] = result.error
        log.payload = payload
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(log, "payload")
        db.commit()
    return base_out





def list_activity_logs(

    db: Session,

    project: int | None = None,

    environment: int | None = None,

    source_type: str | None = None,

    limit: int = 50,

) -> list[ActivityLog]:

    query = db.query(ActivityLog)

    if project is not None:

        query = query.filter(ActivityLog.project == str(project))

    if environment is not None:

        query = query.filter(ActivityLog.environment == str(environment))

    if source_type:

        query = query.filter(ActivityLog.source_type == source_type)
    else:
        query = query.filter(ActivityLog.source_type.in_(["gitlab", "database", "api-monitor", "k8s"]))

    return query.order_by(ActivityLog.occurred_at.desc()).limit(limit).all()


async def backfill_missing_commit_times(
    db: Session,
    logs: list[ActivityLog],
    *,
    limit: int = 30,
) -> None:
    from app.repo_service import extract_commit_sha, fetch_commit_time

    updated = 0
    for log in logs:
        if updated >= limit:
            break
        payload = dict(log.payload or {})
        if payload.get("committed_at"):
            continue
        sha = extract_commit_sha(payload)
        repo = payload.get("repo")
        if not sha or not repo:
            continue
        provider = str(payload.get("provider") or log.source_type or "gitlab")
        if provider not in {"gitlab", "github"}:
            continue
        committed_at = await fetch_commit_time(provider, str(repo), str(sha))
        if not committed_at:
            continue
        payload["committed_at"] = committed_at
        log.payload = payload
        updated += 1
    if updated:
        db.commit()





def create_activity_log(db: Session, **kwargs: Any) -> ActivityLog:

    log = ActivityLog(**kwargs)

    db.add(log)

    db.commit()

    db.refresh(log)

    return log





def handle_database_webhook(db: Session, payload: DatabaseWebhookPayload) -> ActivityLog:

    sub: Subscription | None = None

    conn: Connection | None = None



    if payload.connection_id:

        conn = db.query(Connection).filter(Connection.id == payload.connection_id).first()

        if conn and conn.subscription:

            sub = conn.subscription

    elif payload.webhook_secret:

        sub = db.query(Subscription).filter(Subscription.webhook_secret == payload.webhook_secret).first()

        if sub:

            conn = sub.connection



    if not conn:

        raise ValueError("Connection not found for webhook payload")

    if sub:
        link_states = sub.link_enabled or {}
        main_enabled = bool(link_states.get("main", sub.enabled))
        if not main_enabled:
            raise ValueError("Subscription is disabled")



    project, environment = _primary_project_environment(db, conn)



    return create_activity_log(

        db,

        subscription_id=sub.id if sub else None,

        connection_id=conn.id,

        project=project,

        environment=environment,

        source_type="database",

        title=f"DB {payload.operation}" + (f" on {payload.table}" if payload.table else ""),

        summary=payload.summary,

        payload={

            "operation": payload.operation,

            "table": payload.table,

            "rows_affected": payload.rows_affected,

            "sql_preview": payload.sql_preview,

        },

        author=payload.author,

    )



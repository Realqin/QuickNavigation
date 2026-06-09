import json

import secrets

from typing import Any



from fastapi import HTTPException

from sqlalchemy import func

from sqlalchemy.orm import Session



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





def _json_contains(column, value: int):

    return func.json_contains(column, json.dumps(value))





def _normalize_connection_payload(payload: dict[str, Any]) -> dict[str, Any]:

    data = dict(payload)

    if data.get("url") is not None:

        data["url"] = str(data["url"]).strip()

    if data.get("name") is not None:

        data["name"] = str(data["name"]).strip()

    if data.get("is_shared"):

        data["projects"] = []

        data["environments"] = []

    if data.get("type") is not None:

        data["type"] = int(data["type"])

    for key in ("projects", "environments"):

        if key in data and data[key] is not None:

            data[key] = [int(item) for item in data[key]]

    sub_links = data.get("sub_links") or []

    cleaned: list[dict[str, Any]] = []

    for item in sub_links:

        if isinstance(item, dict):

            name = str(item.get("name", "")).strip()

            url = str(item.get("url", "")).strip()

            is_reachable = item.get("is_reachable")

            last_checked_at = item.get("last_checked_at")

        else:

            name = str(getattr(item, "name", "")).strip()

            url = str(getattr(item, "url", "")).strip()

            is_reachable = getattr(item, "is_reachable", None)

            last_checked_at = getattr(item, "last_checked_at", None)

        if name and url:

            row: dict[str, Any] = {"name": name, "url": url}

            if is_reachable is not None:

                row["is_reachable"] = is_reachable

            if last_checked_at is not None:

                row["last_checked_at"] = last_checked_at

            cleaned.append(row)

    data["sub_links"] = cleaned

    return data





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





def _ensure_dict_id(db: Session, dict_type: str, item_id: int, field_label: str) -> None:

    exists = get_dict_item(db, item_id, dict_type)

    if not exists:

        raise HTTPException(

            status_code=400,

            detail=f"{field_label} ID {item_id} 不存在，请先在字典中配置",

        )





def _validate_connection_dict_values(db: Session, data: dict[str, Any]) -> None:

    if data.get("is_shared"):

        return

    projects = data.get("projects")

    if projects is not None:

        if not projects:

            raise HTTPException(status_code=400, detail="至少选择一个项目")

        for item_id in projects:

            _ensure_dict_id(db, DICT_PROJECT, int(item_id), "项目")

    environments = data.get("environments")

    if environments is not None:

        if not environments:

            raise HTTPException(status_code=400, detail="至少选择一个环境")

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

    return False





def create_dict_item(db: Session, data: DictItemCreate) -> DictItem:

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

    if "type" in payload:

        item.dict_type = payload.pop("type")

    for key, value in payload.items():

        setattr(item, key, value)

    db.commit()

    db.refresh(item)

    return item





def delete_dict_item(db: Session, item: DictItem) -> None:

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

) -> list[Connection]:

    query = db.query(Connection)

    if name:

        query = query.filter(Connection.name.contains(name))

    if project is not None:

        query = query.filter(_json_contains(Connection.projects, project))

    if environment is not None:

        query = query.filter(_json_contains(Connection.environments, environment))

    return query.order_by(Connection.sort_order.asc(), Connection.id.asc()).all()





def get_home_data(db: Session, project: int, environment: int) -> dict[str, Any]:

    shared = (

        db.query(Connection)

        .filter(Connection.is_shared.is_(True))

        .order_by(Connection.sort_order.asc(), Connection.id.asc())

        .all()

    )

    scoped = (

        db.query(Connection)

        .filter(

            Connection.is_shared.is_(False),

            _json_contains(Connection.projects, project),

            _json_contains(Connection.environments, environment),

        )

        .order_by(Connection.sort_order.asc(), Connection.id.asc())

        .all()

    )

    return {

        "shared": shared,

        "scoped": scoped,

        "projects": list_dict_items(db, DICT_PROJECT),

        "environments": list_dict_items(db, DICT_ENVIRONMENT),

        "labels": list_dict_items(db, DICT_LABEL),

    }





def create_connection(db: Session, data: ConnectionCreate) -> Connection:

    payload = _normalize_connection_payload(data.model_dump())

    _validate_connection_dict_values(db, payload)

    conn = Connection(**payload)

    db.add(conn)

    db.commit()

    db.refresh(conn)

    return conn





def update_connection(db: Session, conn: Connection, data: ConnectionUpdate) -> Connection:

    payload = data.model_dump(exclude_unset=True)

    merged = {

        "is_shared": payload.get("is_shared", conn.is_shared),

        "projects": payload.get("projects", conn.projects or []),

        "environments": payload.get("environments", conn.environments or []),

        "type": payload.get("type", conn.type),

    }

    merged = _normalize_connection_payload(merged)

    _validate_connection_dict_values(db, merged)



    for key, value in payload.items():

        setattr(conn, key, value)

    if conn.is_shared:

        conn.projects = []

        conn.environments = []



    db.commit()

    db.refresh(conn)

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





def create_subscription(db: Session, data: SubscriptionCreate) -> Subscription:

    sub = Subscription(

        connection_id=data.connection_id,

        enabled=data.enabled,

        github_repo=data.github_repo,

        github_events=data.github_events,

        db_filter=data.db_filter,

        notify_homepage=data.notify_homepage,

        webhook_secret=secrets.token_hex(16),

    )

    db.add(sub)

    db.commit()

    db.refresh(sub)

    return sub





def update_subscription(db: Session, sub: Subscription, data: SubscriptionUpdate) -> Subscription:

    for key, value in data.model_dump(exclude_unset=True).items():

        setattr(sub, key, value)

    db.commit()

    db.refresh(sub)

    return sub





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

    return query.order_by(ActivityLog.occurred_at.desc()).limit(limit).all()





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

    if sub and not sub.enabled:

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



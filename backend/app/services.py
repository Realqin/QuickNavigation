import json

import secrets

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

            raise HTTPException(status_code=400, detail="系统默认分组不可修改名称")

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

        raise HTTPException(status_code=400, detail="系统默认分组不可删除")

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

    conn = Connection(**payload)

    db.add(conn)

    db.commit()

    db.refresh(conn)

    ensure_gitlab_subscription(db, conn)

    ensure_database_subscription(db, conn)

    return conn





def update_connection(db: Session, conn: Connection, data: ConnectionUpdate) -> Connection:

    payload = data.model_dump(exclude_unset=True)

    merged = {

        "group_id": payload.get("group_id", conn.group_id),

        "is_shared": payload.get("is_shared", conn.is_shared),

        "projects": payload.get("projects", conn.projects or []),

        "environments": payload.get("environments", conn.environments or []),

        "type": payload.get("type", conn.type),

    }

    merged = _normalize_connection_payload(merged)

    _validate_connection_dict_values(db, merged)



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
    return {
        item.id
        for item in items
        if "database" in item.name.lower() or "数据库" in item.name
    }


def _subscription_label_ids(db: Session) -> set[int]:
    return _gitlab_label_ids(db) | _database_label_ids(db)


def connection_is_gitlab_type(db: Session, conn: Connection) -> bool:
    return conn.type in _gitlab_label_ids(db)


def connection_is_database_type(db: Session, conn: Connection) -> bool:
    return conn.type in _database_label_ids(db)


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


def list_gitlab_subscription_trees(
    db: Session,
    project: int | None = None,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    sync_gitlab_subscriptions(db)
    sync_database_subscriptions(db)
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
    return trees


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
    from app.repo_service import extract_commit_sha, fetch_commit_diff

    payload = dict(log.payload or {})
    commit_sha = extract_commit_sha(payload)
    repo = payload.get("repo")
    provider = str(payload.get("provider") or "github")
    if not commit_sha or not repo:
        return {
            "log_id": log.id,
            "commit_sha": commit_sha,
            "diff": payload.get("diff") or "",
            "repo": repo,
            "branch": payload.get("branch"),
            "provider": provider,
        }

    cached = payload.get("diff")
    if isinstance(cached, str) and cached:
        return {
            "log_id": log.id,
            "commit_sha": commit_sha,
            "diff": cached,
            "repo": repo,
            "branch": payload.get("branch"),
            "provider": provider,
        }

    diff = await fetch_commit_diff(provider, str(repo), str(commit_sha))
    payload["diff"] = diff
    log.payload = payload
    db.commit()
    db.refresh(log)
    return {
        "log_id": log.id,
        "commit_sha": commit_sha,
        "diff": diff,
        "repo": repo,
        "branch": payload.get("branch"),
        "provider": provider,
    }





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
        query = query.filter(ActivityLog.source_type.in_(["gitlab", "database"]))

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



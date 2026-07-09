"""连接类型与菜单权限映射，控制连接管理中的可见与可操作范围。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.menu_permissions import user_has_menu
from app.models import Connection, User
from app.services import get_label_kind

# 需要按菜单权限管控的连接类型
PERMISSION_CONTROLLED_KINDS: frozenset[str] = frozenset(
    {"k8s", "database", "redis", "mqtt", "terminal", "kafka"}
)

# 不受连接类型权限管控（有页面访问权即可见）
UNCONTROLLED_KINDS: frozenset[str] = frozenset({"gitlab", "other"})

# 受控类型 -> 菜单权限 key
CONNECTION_KIND_MENU_KEYS: dict[str, str] = {
    "k8s": "serviceMonitor",
    "database": "methodDatabase",
    "redis": "methodRedis",
    "mqtt": "methodMqtt",
    "terminal": "methodTerminal",
    "kafka": "methodKafka",
}

CONNECTION_KIND_LABELS: dict[str, str] = {
    "k8s": "K8s",
    "database": "MySQL/数据库",
    "redis": "Redis",
    "mqtt": "MQTT",
    "terminal": "终端模拟器",
    "gitlab": "GitLab",
    "kafka": "Kafka",
    "other": "其他",
}


def is_permission_controlled_kind(kind: str) -> bool:
    return kind in PERMISSION_CONTROLLED_KINDS


def connection_kind_menu_key(kind: str) -> str | None:
    return CONNECTION_KIND_MENU_KEYS.get(kind)


def user_can_access_connection_kind(user: User | None, kind: str) -> bool:
    if not user:
        return False
    if user.is_admin:
        return True
    if kind in UNCONTROLLED_KINDS:
        return True
    menu_key = connection_kind_menu_key(kind)
    if not menu_key:
        return True
    return user_has_menu(user, menu_key)


def user_allowed_connection_kinds(user: User | None) -> set[str]:
    if not user:
        return set()
    allowed = set(UNCONTROLLED_KINDS)
    if user.is_admin:
        return allowed | set(PERMISSION_CONTROLLED_KINDS)
    for kind in PERMISSION_CONTROLLED_KINDS:
        menu_key = CONNECTION_KIND_MENU_KEYS[kind]
        if user_has_menu(user, menu_key):
            allowed.add(kind)
    return allowed


def get_connection_kind(db: Session, conn: Connection) -> str:
    return get_label_kind(db, int(conn.type))


def user_can_access_connection(db: Session, user: User | None, conn: Connection) -> bool:
    return user_can_access_connection_kind(user, get_connection_kind(db, conn))


def filter_connections_for_user(
    db: Session,
    user: User | None,
    connections: list[Connection],
) -> list[Connection]:
    if not user or user.is_admin:
        return connections
    allowed = user_allowed_connection_kinds(user)
    return [conn for conn in connections if get_connection_kind(db, conn) in allowed]


def ensure_connection_type_permission(db: Session, user: User, type_id: int) -> None:
    kind = get_label_kind(db, int(type_id))
    if not is_permission_controlled_kind(kind):
        return
    if not user_can_access_connection_kind(user, kind):
        label = CONNECTION_KIND_LABELS.get(kind, kind)
        raise HTTPException(status_code=403, detail=f"无 {label} 连接管理权限")


def ensure_connection_access(db: Session, user: User, conn: Connection) -> None:
    if not user_can_access_connection(db, user, conn):
        kind = get_connection_kind(db, conn)
        label = CONNECTION_KIND_LABELS.get(kind, kind)
        raise HTTPException(status_code=403, detail=f"无 {label} 连接查看或操作权限")


def user_has_any_connection_permission(user: User | None) -> bool:
    if not user:
        return False
    if user.is_admin:
        return True
    for kind in PERMISSION_CONTROLLED_KINDS:
        if user_has_menu(user, CONNECTION_KIND_MENU_KEYS[kind]):
            return True
    return False

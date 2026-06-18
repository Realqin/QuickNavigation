from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.connection_test_service import _test_tcp_connection
from app.models import MqttConsoleConnection
from app.schemas import (
    ConnectionTestOut,
    MqttConsoleConnectOut,
    MqttConsoleConnectionCreate,
    MqttConsoleConnectionOut,
    MqttConsoleConnectionTestRequest,
    MqttConsoleConnectionUpdate,
    MqttConsoleSubscriptionsUpdate,
    MqttSubscriptionItem,
)


def _normalize_subscriptions(raw: list | None) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in raw or []:
        if isinstance(item, dict):
            topic = str(item.get("topic", "")).strip()
            name = str(item.get("name", "")).strip()
        else:
            topic = str(getattr(item, "topic", "")).strip()
            name = str(getattr(item, "name", "")).strip()
        if topic:
            cleaned.append({"topic": topic, "name": name or topic})
    return cleaned


def _subscription_items(raw: list | None) -> list[MqttSubscriptionItem]:
    return [MqttSubscriptionItem(**item) for item in _normalize_subscriptions(raw)]


def _to_out(conn: MqttConsoleConnection) -> MqttConsoleConnectionOut:
    return MqttConsoleConnectionOut(
        id=conn.id,
        name=conn.name,
        host=conn.host,
        port=conn.port,
        username=conn.username,
        password_set=bool((conn.password or "").strip()),
        mqtt_subscriptions=_subscription_items(conn.mqtt_subscriptions),
        sort_order=conn.sort_order,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


def list_mqtt_console_connections(db: Session) -> list[MqttConsoleConnectionOut]:
    rows = (
        db.query(MqttConsoleConnection)
        .order_by(MqttConsoleConnection.sort_order.asc(), MqttConsoleConnection.id.asc())
        .all()
    )
    return [_to_out(row) for row in rows]


def get_mqtt_console_connection(db: Session, connection_id: int) -> MqttConsoleConnection:
    conn = db.query(MqttConsoleConnection).filter(MqttConsoleConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="MQTT 连接不存在")
    return conn


def create_mqtt_console_connection(
    db: Session,
    data: MqttConsoleConnectionCreate,
) -> MqttConsoleConnectionOut:
    name = data.name.strip()
    host = data.host.strip()
    if not name:
        raise HTTPException(status_code=400, detail="连接名称不能为空")
    if not host:
        raise HTTPException(status_code=400, detail="Broker 地址不能为空")

    max_sort = db.query(MqttConsoleConnection.sort_order).order_by(
        MqttConsoleConnection.sort_order.desc()
    ).first()
    next_sort = (max_sort[0] if max_sort else -1) + 1

    conn = MqttConsoleConnection(
        name=name,
        host=host,
        port=int(data.port or 1883),
        username=(data.username or "").strip() or None,
        password=(data.password or "").strip() or None,
        mqtt_subscriptions=[],
        sort_order=next_sort,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return _to_out(conn)


def update_mqtt_console_connection(
    db: Session,
    conn: MqttConsoleConnection,
    data: MqttConsoleConnectionUpdate,
) -> MqttConsoleConnectionOut:
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="连接名称不能为空")
        conn.name = name

    if data.host is not None:
        host = data.host.strip()
        if not host:
            raise HTTPException(status_code=400, detail="Broker 地址不能为空")
        conn.host = host

    if data.port is not None:
        conn.port = int(data.port)

    if data.username is not None:
        conn.username = data.username.strip() or None

    if data.password is not None:
        password = data.password.strip()
        if password:
            conn.password = password

    db.commit()
    db.refresh(conn)
    return _to_out(conn)


def delete_mqtt_console_connection(db: Session, conn: MqttConsoleConnection) -> None:
    db.delete(conn)
    db.commit()


def test_mqtt_console_connection(data: MqttConsoleConnectionTestRequest) -> ConnectionTestOut:
    host = data.host.strip()
    if not host:
        return ConnectionTestOut(ok=False, message="Broker 地址不能为空")
    return _test_tcp_connection(host, int(data.port or 1883), label="MQTT")


def update_mqtt_console_subscriptions(
    db: Session,
    conn: MqttConsoleConnection,
    data: MqttConsoleSubscriptionsUpdate,
) -> MqttConsoleConnectionOut:
    conn.mqtt_subscriptions = _normalize_subscriptions(
        [item.model_dump() for item in data.subscriptions]
    )
    db.commit()
    db.refresh(conn)
    return _to_out(conn)


def prepare_mqtt_console_connect(conn: MqttConsoleConnection) -> MqttConsoleConnectOut:
    host = conn.host.strip()
    port = int(conn.port or 1883)
    return MqttConsoleConnectOut(
        connection_id=conn.id,
        connection_name=conn.name,
        host=host,
        port=port,
        broker_url=f"mqtt://{host}:{port}",
        username=conn.username or "",
        password=conn.password or "",
        subscriptions=_subscription_items(conn.mqtt_subscriptions),
    )

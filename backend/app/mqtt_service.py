from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Connection
from app.services import connection_is_mqtt_type


def prepare_mqtt_console_config(db: Session, conn: Connection) -> dict:
    if not connection_is_mqtt_type(db, conn):
        raise HTTPException(status_code=400, detail="仅 MQTT 类型连接支持控制台")

    host = (conn.host or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="MQTT 连接未配置主机")

    port = int(conn.port or 1883)
    ws_path = (conn.mqtt_ws_path or "").strip() or "/mqtt"
    if not ws_path.startswith("/"):
        ws_path = f"/{ws_path}"

    subscriptions = []
    for item in conn.mqtt_subscriptions or []:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic", "")).strip()
        if not topic:
            continue
        name = str(item.get("name", "")).strip() or topic
        subscriptions.append({"topic": topic, "name": name})

    return {
        "connection_id": conn.id,
        "connection_name": conn.name,
        "host": host,
        "port": port,
        "broker_url": f"mqtt://{host}:{port}",
        "ws_path": ws_path,
        "username": conn.username or "",
        "password": conn.password or "",
        "subscriptions": subscriptions,
        "use_bridge": True,
        "bridge_path": f"/ws/mqtt/{conn.id}",
    }

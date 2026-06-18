from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.connection_test_service import _test_kafka_brokers
from app.kafka_broker_utils import normalize_kafka_brokers_field, validate_kafka_brokers
from app.models import KafkaConsoleConnection
from app.schemas import (
    ConnectionTestOut,
    KafkaConsoleConnectionCreate,
    KafkaConsoleConnectionOut,
    KafkaConsoleConnectionTestRequest,
    KafkaConsoleConnectionUpdate,
)


def _to_out(conn: KafkaConsoleConnection) -> KafkaConsoleConnectionOut:
    return KafkaConsoleConnectionOut(
        id=conn.id,
        name=conn.name,
        brokers=conn.brokers,
        username=conn.username,
        password_set=bool((conn.password or "").strip()),
        sort_order=conn.sort_order,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


def list_kafka_console_connections(db: Session) -> list[KafkaConsoleConnectionOut]:
    rows = (
        db.query(KafkaConsoleConnection)
        .order_by(KafkaConsoleConnection.sort_order.asc(), KafkaConsoleConnection.id.asc())
        .all()
    )
    return [_to_out(row) for row in rows]


def get_kafka_console_connection(db: Session, connection_id: int) -> KafkaConsoleConnection:
    conn = db.query(KafkaConsoleConnection).filter(KafkaConsoleConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Kafka 连接不存在")
    return conn


def create_kafka_console_connection(
    db: Session,
    data: KafkaConsoleConnectionCreate,
) -> KafkaConsoleConnectionOut:
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="连接名称不能为空")
    try:
        normalized_brokers, _ = normalize_kafka_brokers_field(data.brokers.strip(), None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    max_sort = db.query(KafkaConsoleConnection.sort_order).order_by(
        KafkaConsoleConnection.sort_order.desc()
    ).first()
    next_sort = (max_sort[0] if max_sort else -1) + 1

    conn = KafkaConsoleConnection(
        name=name,
        brokers=normalized_brokers,
        username=(data.username or "").strip() or None,
        password=(data.password or "").strip() or None,
        sort_order=next_sort,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return _to_out(conn)


def update_kafka_console_connection(
    db: Session,
    conn: KafkaConsoleConnection,
    data: KafkaConsoleConnectionUpdate,
) -> KafkaConsoleConnectionOut:
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="连接名称不能为空")
        conn.name = name

    if data.brokers is not None:
        try:
            normalized_brokers, _ = normalize_kafka_brokers_field(data.brokers.strip(), None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        conn.brokers = normalized_brokers

    if data.username is not None:
        conn.username = data.username.strip() or None

    if data.password is not None:
        password = data.password.strip()
        if password:
            conn.password = password

    db.commit()
    db.refresh(conn)
    return _to_out(conn)


def delete_kafka_console_connection(db: Session, conn: KafkaConsoleConnection) -> None:
    db.delete(conn)
    db.commit()


def test_kafka_console_connection(data: KafkaConsoleConnectionTestRequest) -> ConnectionTestOut:
    try:
        brokers = validate_kafka_brokers(data.brokers.strip(), None)
    except ValueError as exc:
        return ConnectionTestOut(ok=False, message=str(exc))
    return _test_kafka_brokers(brokers)

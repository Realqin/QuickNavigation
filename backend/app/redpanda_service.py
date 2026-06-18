import logging
import os
import time
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.kafka_broker_utils import LOCAL_HOST_ALIASES, parse_kafka_brokers
from app.models import Connection, KafkaConsoleConnection
from app.services import connection_is_kafka_type

logger = logging.getLogger(__name__)

_kafka_console_config_snapshot: str | None = None


def build_redpanda_public_base(request_host: str | None = None) -> str:
    if request_host:
        hostname = request_host.split(":")[0].strip()
        if hostname:
            return f"http://{hostname}:{settings.redpanda_public_port}"
    configured = settings.public_webhook_base_url.strip()
    if configured:
        parsed = urlparse(configured)
        if parsed.hostname and parsed.hostname not in LOCAL_HOST_ALIASES:
            scheme = parsed.scheme or "http"
            return f"{scheme}://{parsed.hostname}:{settings.redpanda_public_port}"
    return f"http://localhost:{settings.redpanda_public_port}"


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _broker_endpoints(conn: Connection) -> list[str]:
    brokers = parse_kafka_brokers(conn.host, conn.port)
    if not brokers:
        raise HTTPException(status_code=400, detail="Kafka 连接未配置集群地址")
    return brokers


def _broker_endpoints_from_text(brokers_text: str) -> list[str]:
    brokers = parse_kafka_brokers(brokers_text, None)
    if not brokers:
        raise HTTPException(status_code=400, detail="Kafka 连接未配置集群地址")
    return brokers


def _render_console_config_from_brokers(
    brokers: list[str],
    *,
    username: str | None = None,
    password: str | None = None,
) -> str:
    broker_lines = "\n".join(f"    - {_yaml_quote(endpoint)}" for endpoint in brokers)
    username = (username or "").strip()
    password = (password or "").strip()
    if username and password:
        sasl_block = f"""  sasl:
    enabled: true
    mechanism: SCRAM-SHA-256
    username: {_yaml_quote(username)}
    password: {_yaml_quote(password)}"""
    else:
        sasl_block = """  sasl:
    enabled: false"""
    return f"""kafka:
  brokers:
{broker_lines}
{sasl_block}
  tls:
    enabled: false
  startup:
    establishConnectionEagerly: false
    maxRetries: 5
    retryInterval: 2s
    maxRetryInterval: 30s
    backoffMultiplier: 2
redpanda:
  adminApi:
    enabled: false
"""


def _render_console_config(conn: Connection) -> str:
    return _render_console_config_from_brokers(
        _broker_endpoints(conn),
        username=conn.username,
        password=conn.password,
    )


def _render_kafka_console_config(conn: KafkaConsoleConnection) -> str:
    return _render_console_config_from_brokers(
        _broker_endpoints_from_text(conn.brokers),
        username=conn.username,
        password=conn.password,
    )


def _read_text_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def snapshot_redpanda_console_config() -> str:
    config_path = settings.redpanda_config_path.strip()
    if not config_path:
        return ""
    return _read_text_file(config_path)


def restore_redpanda_console_config(snapshot: str | None) -> None:
    if snapshot is None:
        return
    config_path = settings.redpanda_config_path.strip()
    if not config_path:
        return
    _write_text_file(config_path, snapshot)
    _wait_for_config_reload()


def _write_text_file(path: str, content: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    try:
        with open(path, encoding="utf-8") as handle:
            written = handle.read()
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Redpanda 配置写入失败：{exc}") from exc
    if written != content:
        raise HTTPException(
            status_code=502,
            detail=f"Redpanda 配置未写入预期路径：{path}",
        )
    logger.info("redpanda config updated: %s", path)


def _list_kafka_connections(db: Session) -> list[Connection]:
    from app.models import Connection as ConnModel
    from app.services import _kafka_label_ids

    kafka_type_ids = _kafka_label_ids(db)
    if not kafka_type_ids:
        return []
    return (
        db.query(ConnModel)
        .filter(ConnModel.type.in_(kafka_type_ids))
        .order_by(ConnModel.id.asc())
        .all()
    )


def sync_kafka_clusters_manifest(db: Session) -> None:
    manifest_path = settings.redpanda_clusters_manifest_path.strip()
    if not manifest_path:
        return

    lines = ["clusters:"]
    for conn in _list_kafka_connections(db):
        try:
            brokers = _broker_endpoints(conn)
            username = _yaml_quote((conn.username or "").strip())
            has_password = "true" if (conn.password or "").strip() else "false"
            lines.append(f"  - id: {conn.id}")
            lines.append(f"    name: {_yaml_quote(conn.name)}")
            lines.append("    brokers:")
            for broker in brokers:
                lines.append(f"      - {_yaml_quote(broker)}")
            lines.append(f"    username: {username}")
            lines.append(f"    has_password: {has_password}")
        except HTTPException:
            continue

    _write_text_file(manifest_path, "\n".join(lines) + "\n")


def _list_kafka_console_connections(db: Session) -> list[KafkaConsoleConnection]:
    return (
        db.query(KafkaConsoleConnection)
        .order_by(KafkaConsoleConnection.id.asc())
        .all()
    )


def sync_kafka_console_clusters_manifest(db: Session) -> None:
    manifest_path = settings.redpanda_clusters_manifest_path.strip()
    if not manifest_path:
        return

    lines = ["clusters:"]
    for conn in _list_kafka_console_connections(db):
        try:
            brokers = _broker_endpoints_from_text(conn.brokers)
            username = _yaml_quote((conn.username or "").strip())
            has_password = "true" if (conn.password or "").strip() else "false"
            lines.append(f"  - id: {conn.id}")
            lines.append(f"    name: {_yaml_quote(conn.name)}")
            lines.append("    brokers:")
            for broker in brokers:
                lines.append(f"      - {_yaml_quote(broker)}")
            lines.append(f"    username: {username}")
            lines.append(f"    has_password: {has_password}")
        except HTTPException:
            continue

    _write_text_file(manifest_path, "\n".join(lines) + "\n")


def sync_connection_to_redpanda(db: Session, conn: Connection) -> None:
    if not connection_is_kafka_type(db, conn):
        raise HTTPException(status_code=400, detail="仅 Kafka 类型连接支持 Redpanda Console")

    config_path = settings.redpanda_config_path.strip()
    if not config_path:
        raise HTTPException(status_code=503, detail="Redpanda Console 未配置")

    _write_text_file(config_path, _render_console_config(conn))
    sync_kafka_clusters_manifest(db)
    _wait_for_config_reload()


def _wait_for_config_reload() -> None:
    delay = max(settings.redpanda_reload_wait_seconds, 0)
    if delay > 0:
        time.sleep(delay)


def prepare_redpanda_open(
    db: Session,
    conn: Connection,
    *,
    public_base: str,
    snapshot_before: str | None = None,
) -> dict:
    sync_connection_to_redpanda(db, conn)
    return {
        "embed_url": f"{public_base.rstrip('/')}/",
        "connection_name": conn.name,
        "snapshot_config": snapshot_before,
    }


def sync_kafka_console_to_redpanda(db: Session, conn: KafkaConsoleConnection) -> None:
    config_path = settings.redpanda_config_path.strip()
    if not config_path:
        raise HTTPException(status_code=503, detail="Redpanda Console 未配置")

    _write_text_file(config_path, _render_kafka_console_config(conn))
    sync_kafka_console_clusters_manifest(db)
    _wait_for_config_reload()


def prepare_kafka_console_redpanda_open(
    db: Session,
    conn: KafkaConsoleConnection,
    *,
    public_base: str,
) -> dict:
    global _kafka_console_config_snapshot
    _kafka_console_config_snapshot = snapshot_redpanda_console_config()
    sync_kafka_console_to_redpanda(db, conn)
    return {
        "embed_url": f"{public_base.rstrip('/')}/",
        "connection_name": conn.name,
    }


def disconnect_kafka_console_redpanda() -> None:
    global _kafka_console_config_snapshot
    snapshot = _kafka_console_config_snapshot
    _kafka_console_config_snapshot = None
    if snapshot is None:
        return
    restore_redpanda_console_config(snapshot)
    logger.info("kafka console disconnected, redpanda config restored")

import logging
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.console_temp import TEMP_EXTERNAL_ALIAS_PREFIX
from app.models import Connection, EmbedConsoleSession

logger = logging.getLogger(__name__)

CONSOLE_DATABASE = "database"
CONSOLE_REDIS = "redis"
CONSOLE_KAFKA = "kafka"
CONSOLE_TERMINAL = "terminal"
CONSOLE_MQTT = "mqtt"

SESSION_STATUS_ACTIVE = "active"
SESSION_STATUS_CLOSED = "closed"


def build_temp_external_alias(session_id: str, connection_name: str) -> str:
    short = session_id.replace("-", "")[:8]
    return f"{TEMP_EXTERNAL_ALIAS_PREFIX}{short}__{connection_name}"


def create_embed_session(
    db: Session,
    conn: Connection,
    console_type: str,
    *,
    temporary: bool = True,
) -> EmbedConsoleSession:
    session_id = str(uuid.uuid4())
    external_alias = (
        build_temp_external_alias(session_id, conn.name)
        if temporary
        else conn.name
    )
    session = EmbedConsoleSession(
        id=session_id,
        connection_id=conn.id,
        console_type=console_type,
        is_temporary=temporary,
        external_alias=external_alias,
        status=SESSION_STATUS_ACTIVE,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_active_embed_session(db: Session, session_id: str) -> EmbedConsoleSession:
    session = (
        db.query(EmbedConsoleSession)
        .filter(
            EmbedConsoleSession.id == session_id,
            EmbedConsoleSession.status == SESSION_STATUS_ACTIVE,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已关闭")
    return session


def update_embed_session(
    db: Session,
    session: EmbedConsoleSession,
    *,
    external_id: str | None = None,
    embed_url: str | None = None,
    snapshot_config: str | None = None,
) -> EmbedConsoleSession:
    if external_id is not None:
        session.external_id = external_id
    if embed_url is not None:
        session.embed_url = embed_url
    if snapshot_config is not None:
        session.snapshot_config = snapshot_config
    db.commit()
    db.refresh(session)
    return session


def close_embed_session(db: Session, session_id: str) -> None:
    session = (
        db.query(EmbedConsoleSession)
        .filter(EmbedConsoleSession.id == session_id)
        .first()
    )
    if not session or session.status == SESSION_STATUS_CLOSED:
        return

    try:
        _cleanup_external_session(session)
    except Exception as exc:
        logger.warning("cleanup embed session %s failed: %s", session_id, exc)
    finally:
        session.status = SESSION_STATUS_CLOSED
        session.closed_at = datetime.utcnow()
        db.commit()


def _cleanup_external_session(session: EmbedConsoleSession) -> None:
    if not session.is_temporary:
        return

    if session.console_type == CONSOLE_DATABASE:
        from app.omnidb_service import delete_omnidb_connection

        if session.external_id:
            delete_omnidb_connection(int(session.external_id))
        return

    if session.console_type == CONSOLE_REDIS:
        from app.redisinsight_service import delete_redisinsight_database

        if session.external_id:
            delete_redisinsight_database(session.external_id)
        return

    if session.console_type == CONSOLE_KAFKA:
        from app.redpanda_service import restore_redpanda_console_config

        restore_redpanda_console_config(session.snapshot_config)
        return

    # terminal / mqtt: 无外部持久实体，仅记录会话状态


def _active_temporary_external_ids(db: Session, console_type: str) -> set[str]:
    rows = (
        db.query(EmbedConsoleSession.external_id)
        .filter(
            EmbedConsoleSession.status == SESSION_STATUS_ACTIVE,
            EmbedConsoleSession.is_temporary.is_(True),
            EmbedConsoleSession.console_type == console_type,
            EmbedConsoleSession.external_id.isnot(None),
        )
        .all()
    )
    return {str(row[0]) for row in rows if row[0]}


def purge_orphan_temporary_external_connections(db: Session) -> None:
    """清理 OmniDB / RedisInsight 中已无活跃会话的临时连接。"""
    from app.omnidb_service import purge_orphan_temporary_omnidb_connections
    from app.redisinsight_service import purge_orphan_temporary_redisinsight_databases

    keep_db = _active_temporary_external_ids(db, CONSOLE_DATABASE)
    keep_redis = _active_temporary_external_ids(db, CONSOLE_REDIS)
    keep_omnidb_ids = {int(item) for item in keep_db if item.isdigit()}
    try:
        purge_orphan_temporary_omnidb_connections(keep_omnidb_ids)
    except Exception as exc:
        logger.warning("purge omnidb temporary connections failed: %s", exc)
    try:
        purge_orphan_temporary_redisinsight_databases(keep_redis)
    except Exception as exc:
        logger.warning("purge redisinsight temporary connections failed: %s", exc)


def purge_temporary_connections_for_connection_method_menu(db: Session, console_type: str) -> None:
    """连接方式菜单：关闭全部临时 embed 会话并删除外部控制台中的临时连接。"""
    from app.omnidb_service import purge_orphan_temporary_omnidb_connections
    from app.redisinsight_service import purge_orphan_temporary_redisinsight_databases

    active_sessions = (
        db.query(EmbedConsoleSession)
        .filter(
            EmbedConsoleSession.status == SESSION_STATUS_ACTIVE,
            EmbedConsoleSession.is_temporary.is_(True),
            EmbedConsoleSession.console_type == console_type,
        )
        .all()
    )
    for session in list(active_sessions):
        close_embed_session(db, session.id)

    try:
        if console_type == CONSOLE_DATABASE:
            purge_orphan_temporary_omnidb_connections(set())
        elif console_type == CONSOLE_REDIS:
            purge_orphan_temporary_redisinsight_databases(set())
    except Exception as exc:
        logger.warning(
            "purge menu temporary connections failed (%s): %s",
            console_type,
            exc,
        )

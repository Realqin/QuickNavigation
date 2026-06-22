from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import ActivityLog, Connection, SchemaSnapshot, Subscription
from app.schemas import (
    ActivityLogOut,
    SchemaMonitorConfigUpdate,
    SchemaMonitorOut,
    SchemaMonitorPingOut,
    SchemaMonitorPingRequest,
)
from app.services import (
    _database_label_ids,
    _primary_project_environment,
    connection_is_database_type,
    create_activity_log,
    sync_database_subscriptions,
)
from app.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

SYSTEM_DATABASES = frozenset({"information_schema", "mysql", "performance_schema", "sys"})
MYSQL_DSN_PATTERN = re.compile(r"^mysql(\+pymysql)?://", re.IGNORECASE)
NAVICAT_MYSQL_PATTERN = re.compile(r"^navicat://conn\.mysql\b", re.IGNORECASE)


@dataclass
class SchemaChange:
    operation: str
    table: str | None
    summary: str
    details: list[str] = field(default_factory=list)
    sql_preview: str | None = None
    before: str | None = None
    after: str | None = None


def _mask_dsn(dsn: str) -> str:
    value = dsn.strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
        if parsed.username:
            password = parsed.password or ""
            masked = "****" if password else ""
            userinfo = f"{parsed.username}:{masked}@" if masked else f"{parsed.username}@"
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            return f"{parsed.scheme}://{userinfo}{host}{port}{parsed.path or ''}"
    except Exception:
        pass
    return value


def _normalize_dsn(dsn: str) -> str:
    value = dsn.strip()
    if value.startswith("mysql://"):
        return "mysql+pymysql://" + value[len("mysql://") :]
    return value


def _is_navicat_mysql_url(value: str | None) -> bool:
    return bool(value and NAVICAT_MYSQL_PATTERN.match(value.strip()))


def _is_mysql_dsn(value: str | None) -> bool:
    return bool(value and MYSQL_DSN_PATTERN.match(value.strip()))


def _query_param(params: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = params.get(key)
        if values and str(values[0]).strip():
            return unquote(str(values[0]).strip())
    return ""


def parse_navicat_mysql_url(url: str) -> dict[str, Any]:
    value = url.strip()
    if not _is_navicat_mysql_url(value):
        raise ValueError("不是有效的 Navicat MySQL 连接串")
    parsed = urlparse(value)
    params = parse_qs(parsed.query, keep_blank_values=True)
    host = _query_param(params, "Conn.Host", "Host")
    username = _query_param(params, "Conn.Username", "Username")
    if not host:
        raise ValueError("Navicat 连接串缺少 Conn.Host")
    if not username:
        raise ValueError("Navicat 连接串缺少 Conn.Username")
    port_raw = _query_param(params, "Conn.Port", "Port") or "3306"
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("Navicat 连接串中的端口无效") from exc
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": _query_param(params, "Conn.Password", "Password"),
        "database": _query_param(params, "Conn.Database", "Conn.Db", "Database"),
        "name": _query_param(params, "Conn.Name", "Name"),
    }


def resolve_schema_dsn(raw: str, password: str | None = None) -> str:
    value = raw.strip()
    if not value:
        return ""
    if _is_navicat_mysql_url(value):
        parsed = parse_navicat_mysql_url(value)
        pwd = (password if password is not None else parsed.get("password") or "").strip()
        return build_dsn_from_parts(
            host=parsed["host"],
            port=int(parsed["port"]),
            username=parsed["username"],
            password=pwd,
            database=parsed.get("database") or None,
        )
    return _normalize_dsn(value)


def _parse_db_filter(sub: Subscription) -> dict[str, Any]:
    raw = sub.db_filter or {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _legacy_dsn_to_connection(dsn: str) -> dict[str, Any]:
    value = _normalize_dsn(dsn.strip())
    parsed = urlparse(value)
    if not parsed.hostname or not parsed.username:
        raise ValueError("无法解析已保存的连接串")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "username": unquote(parsed.username),
        "password": unquote(parsed.password or ""),
    }


def _resolve_monitor_connection(monitor: dict[str, Any]) -> dict[str, Any]:
    data = dict(monitor)
    host = str(data.get("host") or "").strip()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    port_raw = data.get("port")
    port = int(port_raw) if port_raw else 3306

    if host and username:
        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
        }

    legacy_dsn = str(data.get("dsn") or "").strip()
    if legacy_dsn:
        if _is_navicat_mysql_url(legacy_dsn):
            parsed = parse_navicat_mysql_url(legacy_dsn)
            return {
                "host": parsed["host"],
                "port": int(parsed["port"]),
                "username": parsed["username"],
                "password": password or parsed.get("password") or "",
            }
        legacy = _legacy_dsn_to_connection(legacy_dsn)
        return {
            "host": legacy["host"],
            "port": int(legacy["port"]),
            "username": legacy["username"],
            "password": password or legacy.get("password") or "",
        }
    return {"host": "", "port": 3306, "username": "", "password": ""}


def _connection_monitor_connection(conn: Connection) -> dict[str, Any]:
    host = str(conn.host or "").strip()
    username = str(conn.username or "").strip()
    password = str(conn.password or "")
    port = int(conn.port or 3306)

    if host and username:
        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
        }

    raw_url = str(conn.url or "").strip()
    if not raw_url:
        return {"host": host, "port": port, "username": username, "password": password}

    try:
        if _is_navicat_mysql_url(raw_url):
            parsed = parse_navicat_mysql_url(raw_url)
            resolved_password = password or str(parsed.get("password") or "")
            resolved_host = host or str(parsed.get("host") or "").strip()
            resolved_username = username or str(parsed.get("username") or "").strip()
            resolved_port = port if conn.port else int(parsed.get("port") or 3306)
            return {
                "host": resolved_host,
                "port": resolved_port,
                "username": resolved_username,
                "password": resolved_password,
            }

        if _is_mysql_dsn(raw_url):
            legacy = _legacy_dsn_to_connection(raw_url)
            resolved_password = password or str(legacy.get("password") or "")
            return {
                "host": host or str(legacy.get("host") or "").strip(),
                "port": port if conn.port else int(legacy.get("port") or 3306),
                "username": username or str(legacy.get("username") or "").strip(),
                "password": resolved_password,
            }
    except ValueError:
        pass

    return {"host": host, "port": port, "username": username, "password": password}


def get_schema_monitor_config(sub: Subscription) -> dict[str, Any]:
    monitor = _parse_db_filter(sub).get("schema_monitor") or {}
    if not isinstance(monitor, dict):
        monitor = {}
    connection = _resolve_monitor_connection(monitor)
    if not (connection["host"] and connection["username"]) and sub.connection:
        fallback = _connection_monitor_connection(sub.connection)
        if fallback["host"] and fallback["username"]:
            connection = fallback
    include = monitor.get("include_databases") or []
    exclude = monitor.get("exclude_databases") or []
    configured = bool(connection["host"] and connection["username"])
    return {
        "host": connection["host"] or None,
        "port": int(connection["port"] or 3306),
        "username": connection["username"] or None,
        "password": connection["password"],
        "password_set": bool(connection["password"]),
        "connection_configured": configured,
        "include_databases": [str(item).strip() for item in include if str(item).strip()],
        "exclude_databases": [str(item).strip() for item in exclude if str(item).strip()],
    }


def _build_monitor_dsn(config: dict[str, Any]) -> str:
    if not config.get("connection_configured"):
        raise ValueError("请先配置数据库 IP、端口和账号")
    return build_dsn_from_parts(
        host=str(config["host"]),
        port=int(config.get("port") or 3306),
        username=str(config["username"]),
        password=str(config.get("password") or ""),
    )


def _is_subscription_link_enabled(sub: Subscription) -> bool:
    states = sub.link_enabled or {}
    return bool(states.get("main", sub.enabled))


def _subscription_monitor_enabled(sub: Subscription) -> bool:
    config = get_schema_monitor_config(sub)
    return _is_subscription_link_enabled(sub) and config["connection_configured"]


def _should_include_database(name: str, include: list[str], exclude: list[str]) -> bool:
    if name in SYSTEM_DATABASES:
        return False
    if include and name not in include:
        return False
    if name in exclude:
        return False
    return True


def _column_signature(column: dict[str, Any]) -> str:
    return "|".join(
        [
            str(column.get("COLUMN_NAME") or ""),
            str(column.get("COLUMN_TYPE") or ""),
            str(column.get("IS_NULLABLE") or ""),
            str(column.get("COLUMN_KEY") or ""),
            str(column.get("EXTRA") or ""),
            str(column.get("COLUMN_DEFAULT") if column.get("COLUMN_DEFAULT") is not None else ""),
        ]
    )


def _index_signature(index: dict[str, Any]) -> str:
    return "|".join(
        [
            str(index.get("INDEX_NAME") or ""),
            str(index.get("NON_UNIQUE") or ""),
            str(index.get("COLUMN_NAME") or ""),
            str(index.get("SEQ_IN_INDEX") or ""),
            str(index.get("INDEX_TYPE") or ""),
        ]
    )


def _table_fingerprint(columns: list[dict[str, Any]], indexes: list[dict[str, Any]]) -> str:
    column_part = ";".join(sorted(_column_signature(item) for item in columns))
    index_part = ";".join(sorted(_index_signature(item) for item in indexes))
    raw = f"columns:{column_part}##indexes:{index_part}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sql_in_clause(prefix: str, values: list[str]) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    placeholders: list[str] = []
    for index, value in enumerate(values):
        key = f"{prefix}_{index}"
        placeholders.append(f":{key}")
        params[key] = value
    return ", ".join(placeholders), params


def fetch_schema_snapshot(
    dsn: str,
    *,
    include_databases: list[str] | None = None,
    exclude_databases: list[str] | None = None,
) -> dict[str, Any]:
    include = include_databases or []
    exclude = exclude_databases or []
    engine = create_engine(
        _normalize_dsn(dsn),
        poolclass=NullPool,
        connect_args={"connect_timeout": 10, "read_timeout": 120, "write_timeout": 120},
    )
    try:
        with engine.connect() as conn:
            databases = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA "
                        "ORDER BY SCHEMA_NAME"
                    )
                )
                if _should_include_database(row[0], include, exclude)
            ]
            if not databases:
                return {
                    "databases": [],
                    "tables": {},
                    "captured_at": datetime.utcnow().isoformat(),
                }

            schema_clause, schema_params = _sql_in_clause("schema", databases)
            table_rows = conn.execute(
                text(
                    "SELECT TABLE_SCHEMA, TABLE_NAME "
                    "FROM information_schema.TABLES "
                    f"WHERE TABLE_SCHEMA IN ({schema_clause}) AND TABLE_TYPE = 'BASE TABLE' "
                    "ORDER BY TABLE_SCHEMA, TABLE_NAME"
                ),
                schema_params,
            ).mappings().all()

            column_rows = conn.execute(
                text(
                    "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
                    "COLUMN_KEY, EXTRA, COLUMN_DEFAULT, ORDINAL_POSITION "
                    "FROM information_schema.COLUMNS "
                    f"WHERE TABLE_SCHEMA IN ({schema_clause}) "
                    "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
                ),
                schema_params,
            ).mappings().all()

            index_rows = conn.execute(
                text(
                    "SELECT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, NON_UNIQUE, COLUMN_NAME, "
                    "SEQ_IN_INDEX, INDEX_TYPE "
                    "FROM information_schema.STATISTICS "
                    f"WHERE TABLE_SCHEMA IN ({schema_clause}) "
                    "ORDER BY TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"
                ),
                schema_params,
            ).mappings().all()

            columns_by_table: dict[str, list[dict[str, Any]]] = {}
            for row in column_rows:
                key = f"{row['TABLE_SCHEMA']}.{row['TABLE_NAME']}"
                columns_by_table.setdefault(key, []).append(dict(row))

            indexes_by_table: dict[str, list[dict[str, Any]]] = {}
            for row in index_rows:
                key = f"{row['TABLE_SCHEMA']}.{row['TABLE_NAME']}"
                indexes_by_table.setdefault(key, []).append(dict(row))

            tables: dict[str, dict[str, Any]] = {}
            for table_row in table_rows:
                schema_name = table_row["TABLE_SCHEMA"]
                table_name = table_row["TABLE_NAME"]
                key = f"{schema_name}.{table_name}"
                column_dicts = columns_by_table.get(key, [])
                index_dicts = indexes_by_table.get(key, [])
                tables[key] = {
                    "schema": schema_name,
                    "table": table_name,
                    "fingerprint": _table_fingerprint(column_dicts, index_dicts),
                    "columns": column_dicts,
                    "indexes": index_dicts,
                }
            return {
                "databases": databases,
                "tables": tables,
                "captured_at": datetime.utcnow().isoformat(),
            }
    finally:
        engine.dispose()


def _describe_column_changes(
    old_columns: list[dict[str, Any]],
    new_columns: list[dict[str, Any]],
) -> list[str]:
    old_map = {item["COLUMN_NAME"]: item for item in old_columns}
    new_map = {item["COLUMN_NAME"]: item for item in new_columns}
    messages: list[str] = []

    for name in sorted(set(new_map) - set(old_map)):
        col = new_map[name]
        messages.append(f"新增列 {name} {col.get('COLUMN_TYPE')}")

    for name in sorted(set(old_map) - set(new_map)):
        messages.append(f"删除列 {name}")

    for name in sorted(set(old_map) & set(new_map)):
        if _column_signature(old_map[name]) != _column_signature(new_map[name]):
            messages.append(
                f"修改列 {name}: {old_map[name].get('COLUMN_TYPE')} -> {new_map[name].get('COLUMN_TYPE')}"
            )
    return messages


def _describe_index_changes(
    old_indexes: list[dict[str, Any]],
    new_indexes: list[dict[str, Any]],
) -> list[str]:
    def index_map(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row.get("INDEX_NAME") or ""), []).append(row)
        return grouped

    old_grouped = index_map(old_indexes)
    new_grouped = index_map(new_indexes)
    messages: list[str] = []

    for name in sorted(set(new_grouped) - set(old_grouped)):
        messages.append(f"新增索引 {name}")

    for name in sorted(set(old_grouped) - set(new_grouped)):
        messages.append(f"删除索引 {name}")

    for name in sorted(set(old_grouped) & set(new_grouped)):
        old_sig = ";".join(sorted(_index_signature(item) for item in old_grouped[name]))
        new_sig = ";".join(sorted(_index_signature(item) for item in new_grouped[name]))
        if old_sig != new_sig:
            messages.append(f"修改索引 {name}")
    return messages


def _format_column_line(column: dict[str, Any]) -> str:
    parts = [
        str(column.get("COLUMN_NAME") or ""),
        str(column.get("COLUMN_TYPE") or ""),
    ]
    if column.get("IS_NULLABLE") == "NO":
        parts.append("NOT NULL")
    column_key = str(column.get("COLUMN_KEY") or "")
    if column_key == "PRI":
        parts.append("PRIMARY KEY")
    elif column_key == "UNI":
        parts.append("UNIQUE")
    elif column_key == "MUL":
        parts.append("INDEX")
    extra = str(column.get("EXTRA") or "").strip()
    if extra:
        parts.append(extra.upper())
    default = column.get("COLUMN_DEFAULT")
    if default is not None:
        parts.append(f"DEFAULT {default}")
    return " ".join(parts)


def _format_columns(columns: list[dict[str, Any]]) -> str:
    if not columns:
        return "（无列定义）"
    return "\n".join(_format_column_line(item) for item in columns)


def _format_indexes(indexes: list[dict[str, Any]]) -> str:
    if not indexes:
        return "（无索引）"
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in indexes:
        name = str(row.get("INDEX_NAME") or "")
        grouped.setdefault(name, []).append(row)
    lines: list[str] = []
    for name in sorted(grouped):
        rows = sorted(grouped[name], key=lambda item: int(item.get("SEQ_IN_INDEX") or 0))
        columns = ", ".join(str(row.get("COLUMN_NAME") or "") for row in rows)
        if name == "PRIMARY":
            lines.append(f"PRIMARY KEY ({columns})")
            continue
        unique = "UNIQUE " if rows[0].get("NON_UNIQUE") == 0 else ""
        index_type = str(rows[0].get("INDEX_TYPE") or "BTREE")
        lines.append(f"{unique}INDEX {name} ({columns}) USING {index_type}")
    return "\n".join(lines)


def _format_table_schema(table: dict[str, Any] | None) -> str:
    if not table:
        return ""
    columns = _format_columns(table.get("columns") or [])
    indexes = _format_indexes(table.get("indexes") or [])
    return f"【列】\n{columns}\n\n【索引】\n{indexes}"


def diff_schema_snapshots(old: dict[str, Any] | None, new: dict[str, Any]) -> list[SchemaChange]:
    if not old:
        return []

    changes: list[SchemaChange] = []
    old_databases = set(old.get("databases") or [])
    new_databases = set(new.get("databases") or [])
    old_tables: dict[str, Any] = old.get("tables") or {}
    new_tables: dict[str, Any] = new.get("tables") or {}

    for database in sorted(new_databases - old_databases):
        changes.append(
            SchemaChange(
                operation="CREATE_DATABASE",
                table=database,
                summary=f"新增数据库 {database}",
                before="（不存在）",
                after=f"数据库 {database}",
                details=[f"新增数据库 {database}"],
            )
        )

    for database in sorted(old_databases - new_databases):
        changes.append(
            SchemaChange(
                operation="DROP_DATABASE",
                table=database,
                summary=f"删除数据库 {database}",
                before=f"数据库 {database}",
                after="（已删除）",
                details=[f"删除数据库 {database}"],
            )
        )

    for table_key in sorted(set(new_tables) - set(old_tables)):
        new_table = new_tables[table_key]
        schema_text = _format_table_schema(new_table)
        changes.append(
            SchemaChange(
                operation="CREATE_TABLE",
                table=table_key,
                summary=f"新增表 {table_key}",
                before="（不存在）",
                after=schema_text,
                details=[f"新增表 {table_key}"],
            )
        )

    for table_key in sorted(set(old_tables) - set(new_tables)):
        old_table = old_tables[table_key]
        schema_text = _format_table_schema(old_table)
        changes.append(
            SchemaChange(
                operation="DROP_TABLE",
                table=table_key,
                summary=f"删除表 {table_key}",
                before=schema_text,
                after="（已删除）",
                details=[f"删除表 {table_key}"],
            )
        )

    for table_key in sorted(set(old_tables) & set(new_tables)):
        old_table = old_tables[table_key]
        new_table = new_tables[table_key]
        if old_table.get("fingerprint") == new_table.get("fingerprint"):
            continue
        details = _describe_column_changes(
            old_table.get("columns") or [],
            new_table.get("columns") or [],
        )
        details.extend(
            _describe_index_changes(
                old_table.get("indexes") or [],
                new_table.get("indexes") or [],
            )
        )
        summary = f"修改表 {table_key}"
        if details:
            summary = f"{summary}：" + "；".join(details[:3])
            if len(details) > 3:
                summary += f" 等 {len(details)} 项"
        changes.append(
            SchemaChange(
                operation="ALTER_TABLE",
                table=table_key,
                summary=summary,
                details=details,
                before=_format_table_schema(old_table),
                after=_format_table_schema(new_table),
                sql_preview="; ".join(details) if details else None,
            )
        )

    return changes


def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    tables = snapshot.get("tables") or {}
    compact_tables = {
        key: {
            "schema": value.get("schema"),
            "table": value.get("table"),
            "fingerprint": value.get("fingerprint"),
            "columns": value.get("columns") or [],
            "indexes": value.get("indexes") or [],
        }
        for key, value in tables.items()
    }
    return {
        "databases": snapshot.get("databases") or [],
        "tables": compact_tables,
        "captured_at": snapshot.get("captured_at"),
    }


def _snapshot_hash(snapshot: dict[str, Any]) -> str:
    payload = {
        "databases": snapshot.get("databases") or [],
        "tables": {
            key: value.get("fingerprint")
            for key, value in (snapshot.get("tables") or {}).items()
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


async def _broadcast_log(log: Any) -> None:
    data = ActivityLogOut.model_validate(log).model_dump(mode="json")
    await ws_manager.broadcast({"type": "log:new", "data": data})


def _change_to_payload(change: SchemaChange) -> dict[str, Any]:
    return {
        "operation": change.operation,
        "table": change.table,
        "summary": change.summary,
        "details": change.details,
        "diff": change.details,
        "before": change.before,
        "after": change.after,
    }


def _build_scan_summary(changes: list[SchemaChange]) -> str:
    parts: list[str] = []
    for change in changes[:6]:
        if change.details:
            parts.append(f"{change.summary}")
        else:
            parts.append(change.summary)
    if len(changes) > 6:
        parts.append(f"等共 {len(changes)} 项变更")
    return "；".join(parts)


def _emit_schema_changes(
    db: Session,
    *,
    sub: Subscription,
    conn: Connection,
    changes: list[SchemaChange],
) -> list[Any]:
    if not changes:
        return []

    project, environment = _primary_project_environment(db, conn)
    log = create_activity_log(
        db,
        subscription_id=sub.id,
        connection_id=conn.id,
        project=project,
        environment=environment,
        source_type="database",
        title=f"结构变更 · {len(changes)} 项",
        summary=_build_scan_summary(changes),
        payload={
            "event": "schema_change",
            "monitor": "snapshot",
            "change_count": len(changes),
            "changes": [_change_to_payload(change) for change in changes],
        },
        author="schema-monitor",
    )
    return [log]


def scan_subscription_schema(db: Session, sub: Subscription, *, baseline_only: bool = False) -> dict[str, Any]:
    sync_database_subscriptions(db)
    db.refresh(sub)
    conn = sub.connection
    if not conn or not connection_is_database_type(db, conn):
        raise ValueError("仅支持数据库类型连接的订阅")

    if not _is_subscription_link_enabled(sub):
        raise ValueError("请先在订阅列表中启用该连接")
    config = get_schema_monitor_config(sub)
    if not config["connection_configured"]:
        raise ValueError("请先配置数据库 IP、端口和账号")

    snapshot_row = (
        db.query(SchemaSnapshot).filter(SchemaSnapshot.subscription_id == sub.id).first()
    )
    had_baseline = bool(snapshot_row and snapshot_row.snapshot)
    now = datetime.utcnow()
    try:
        new_snapshot = fetch_schema_snapshot(
            _build_monitor_dsn(config),
            include_databases=config["include_databases"],
            exclude_databases=config["exclude_databases"],
        )
        compact = _compact_snapshot(new_snapshot)
        changes: list[SchemaChange] = []
        if had_baseline and not baseline_only:
            changes = diff_schema_snapshots(snapshot_row.snapshot, compact)

        if not snapshot_row:
            snapshot_row = SchemaSnapshot(subscription_id=sub.id, snapshot=compact)
            db.add(snapshot_row)
        else:
            snapshot_row.snapshot = compact
        snapshot_row.snapshot_hash = _snapshot_hash(compact)
        snapshot_row.last_scan_at = now
        snapshot_row.last_error = None
        db.commit()
        db.refresh(snapshot_row)

        logs = _emit_schema_changes(db, sub=sub, conn=conn, changes=changes)
        return {
            "subscription_id": sub.id,
            "changes_detected": len(changes),
            "logs_created": len(logs),
            "logs": logs,
            "snapshot": snapshot_row,
            "was_first_scan": not had_baseline,
        }
    except Exception as exc:
        logger.exception("Schema scan failed for subscription %s", sub.id)
        if snapshot_row:
            snapshot_row.last_scan_at = now
            snapshot_row.last_error = str(exc)
            db.commit()
        raise


async def scan_subscription_schema_async(
    db: Session,
    sub: Subscription,
    *,
    baseline_only: bool = False,
) -> dict[str, Any]:
    result = await asyncio.to_thread(scan_subscription_schema, db, sub, baseline_only=baseline_only)
    for log in result.get("logs") or []:
        await _broadcast_log(log)
    return result


def clear_schema_change_logs(db: Session, subscription_id: int) -> int:
    rows = (
        db.query(ActivityLog)
        .filter(ActivityLog.subscription_id == subscription_id)
        .all()
    )
    deleted = 0
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if payload.get("event") == "schema_change":
            db.delete(row)
            deleted += 1
    if deleted:
        db.commit()
    return deleted


async def reset_schema_monitor_baseline(db: Session, sub: Subscription) -> dict[str, Any]:
    deleted_logs = clear_schema_change_logs(db, sub.id)
    result = await scan_subscription_schema_async(db, sub, baseline_only=True)
    snapshot = result.get("snapshot")
    if isinstance(snapshot, dict):
        snapshot_data = snapshot.get("snapshot")
    else:
        snapshot_data = snapshot.snapshot if snapshot else None
    table_count = len((snapshot_data or {}).get("tables") or {})
    database_count = len((snapshot_data or {}).get("databases") or [])
    return {
        "subscription_id": sub.id,
        "deleted_logs": deleted_logs,
        "changes_detected": 0,
        "logs_created": 0,
        "has_baseline": bool(snapshot_data),
        "database_count": database_count,
        "table_count": table_count,
        "message": (
            f"已清除 {deleted_logs} 条结构变更日志，并重新生成基准快照"
            f"（{database_count} 库 / {table_count} 表）"
        ),
    }


def list_schema_monitor_targets(db: Session) -> list[Subscription]:
    sync_database_subscriptions(db)
    label_ids = _database_label_ids(db)
    if not label_ids:
        return []
    subs = (
        db.query(Subscription)
        .join(Connection)
        .options(joinedload(Subscription.connection))
        .filter(Connection.type.in_(label_ids))
        .all()
    )
    return [sub for sub in subs if _subscription_monitor_enabled(sub)]


def get_schema_monitor_status(db: Session, sub: Subscription) -> SchemaMonitorOut:
    if not sub.connection or not connection_is_database_type(db, sub.connection):
        raise ValueError("仅支持数据库类型连接的订阅")
    config = get_schema_monitor_config(sub)
    snapshot_row = (
        db.query(SchemaSnapshot).filter(SchemaSnapshot.subscription_id == sub.id).first()
    )
    return SchemaMonitorOut(
        subscription_id=sub.id,
        enabled=_is_subscription_link_enabled(sub),
        host=config["host"],
        port=int(config.get("port") or 3306),
        username=config["username"],
        password_set=config["password_set"],
        connection_configured=config["connection_configured"],
        include_databases=config["include_databases"],
        exclude_databases=config["exclude_databases"],
        interval_seconds=settings.schema_monitor_interval_seconds,
        last_scan_at=snapshot_row.last_scan_at if snapshot_row else None,
        last_error=snapshot_row.last_error if snapshot_row else None,
        has_baseline=bool(snapshot_row and snapshot_row.snapshot),
        database_count=len((snapshot_row.snapshot or {}).get("databases") or []) if snapshot_row else 0,
        table_count=len((snapshot_row.snapshot or {}).get("tables") or {}) if snapshot_row else 0,
    )


def update_schema_monitor_config(
    db: Session,
    sub: Subscription,
    data: SchemaMonitorConfigUpdate,
) -> SchemaMonitorOut:
    if not sub.connection or not connection_is_database_type(db, sub.connection):
        raise ValueError("仅支持数据库类型连接的订阅")

    db_filter = dict(_parse_db_filter(sub))
    monitor = dict(db_filter.get("schema_monitor") or {})
    payload = data.model_dump(exclude_unset=True)

    monitor.pop("enabled", None)
    current = _resolve_monitor_connection(monitor)
    connection_fields_provided = any(
        key in payload and payload[key] is not None
        for key in ("host", "port", "username", "password")
    )
    if connection_fields_provided:
        host = (
            str(payload["host"]).strip()
            if "host" in payload and payload["host"] is not None
            else str(current["host"] or "").strip()
        )
        username = (
            str(payload["username"]).strip()
            if "username" in payload and payload["username"] is not None
            else str(current["username"] or "").strip()
        )
        port = (
            int(payload["port"])
            if "port" in payload and payload["port"] is not None
            else int(current["port"] or 3306)
        )
        if "password" in payload and payload["password"] is not None:
            password = str(payload["password"]).strip() or str(current["password"] or "")
        else:
            password = str(current["password"] or "")

        if not host:
            raise ValueError("请填写数据库 IP")
        if not username:
            raise ValueError("请填写数据库账号")
        monitor["host"] = host
        monitor["port"] = port
        monitor["username"] = username
        monitor["password"] = password
        monitor.pop("dsn", None)
    if "include_databases" in payload and payload["include_databases"] is not None:
        monitor["include_databases"] = [item.strip() for item in payload["include_databases"] if item.strip()]
    if "exclude_databases" in payload and payload["exclude_databases"] is not None:
        monitor["exclude_databases"] = [item.strip() for item in payload["exclude_databases"] if item.strip()]

    db_filter["schema_monitor"] = monitor
    sub.db_filter = db_filter
    db.commit()
    db.refresh(sub)
    return get_schema_monitor_status(db, sub)


def _resolve_ping_connection(
    sub: Subscription,
    data: SchemaMonitorPingRequest | None = None,
) -> dict[str, Any]:
    config = get_schema_monitor_config(sub)
    payload = data.model_dump(exclude_unset=True) if data else {}
    host = (
        str(payload["host"]).strip()
        if payload.get("host") is not None
        else str(config.get("host") or "").strip()
    )
    username = (
        str(payload["username"]).strip()
        if payload.get("username") is not None
        else str(config.get("username") or "").strip()
    )
    port = (
        int(payload["port"])
        if payload.get("port") is not None
        else int(config.get("port") or 3306)
    )
    if payload.get("password") is not None:
        password = str(payload["password"]).strip() or str(config.get("password") or "")
    else:
        password = str(config.get("password") or "")

    if not host:
        raise ValueError("请填写数据库 IP")
    if not username:
        raise ValueError("请填写数据库账号")
    return {"host": host, "port": port, "username": username, "password": password}


def ping_schema_monitor_connection(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
) -> SchemaMonitorPingOut:
    dsn = build_dsn_from_parts(host=host, port=port, username=username, password=password)
    engine = create_engine(
        dsn,
        poolclass=NullPool,
        connect_args={"connect_timeout": 10, "read_timeout": 10, "write_timeout": 10},
    )
    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return SchemaMonitorPingOut(
            ok=True,
            message=f"连接成功（MySQL {version}）",
            latency_ms=latency_ms,
        )
    except Exception as exc:
        return SchemaMonitorPingOut(ok=False, message=f"连接失败：{exc}")
    finally:
        engine.dispose()


def ping_schema_monitor_for_subscription(
    db: Session,
    sub: Subscription,
    data: SchemaMonitorPingRequest | None = None,
) -> SchemaMonitorPingOut:
    if not sub.connection or not connection_is_database_type(db, sub.connection):
        raise ValueError("仅支持数据库类型连接的订阅")
    connection = _resolve_ping_connection(sub, data)
    return ping_schema_monitor_connection(**connection)


def build_dsn_from_parts(
    *,
    host: str,
    port: int,
    username: str,
    password: str = "",
    database: str | None = None,
) -> str:
    user = quote_plus(username)
    db_part = f"/{database}" if database else ""
    if password:
        pwd = quote_plus(password)
        return f"mysql+pymysql://{user}:{pwd}@{host}:{port}{db_part}"
    return f"mysql+pymysql://{user}@{host}:{port}{db_part}"

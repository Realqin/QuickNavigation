"""系统操作日志：记录用户在平台内的行为。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.menu_permissions import PAGE_LABELS
from app.models import OperationLog, User

ACTION_LABELS = {
    "create": "新增",
    "update": "编辑",
    "delete": "删除",
    "login": "登录",
    "logout": "退出",
    "open": "打开",
    "other": "操作",
}

_API_AUDIT_RULES: list[tuple[str, str, str, str]] = [
    (r"^POST /api/connections$", "create", "连接", "新增连接"),
    (r"^PUT /api/connections/\d+$", "update", "连接", "编辑连接"),
    (r"^DELETE /api/connections/\d+$", "delete", "连接", "删除连接"),
    (r"^POST /api/connections/batch-delete$", "delete", "连接", "批量删除连接"),
    (r"^POST /api/dict$", "create", "字典", "新增字典项"),
    (r"^PATCH /api/dict/\d+$", "update", "字典", "编辑字典项"),
    (r"^DELETE /api/dict/\d+$", "delete", "字典", "删除字典项"),
    (r"^POST /api/k8s/clusters$", "create", "K8s集群", "新增 K8s 集群"),
    (r"^PUT /api/k8s/clusters/\d+$", "update", "K8s集群", "编辑 K8s 集群"),
    (r"^DELETE /api/k8s/clusters/\d+$", "delete", "K8s集群", "删除 K8s 集群"),
    (r"^POST /api/llm/configs$", "create", "LLM配置", "新增 LLM 配置"),
    (r"^PUT /api/llm/configs/[^/]+$", "update", "LLM配置", "编辑 LLM 配置"),
    (r"^DELETE /api/llm/configs/[^/]+$", "delete", "LLM配置", "删除 LLM 配置"),
    (r"^POST /api/prompts$", "create", "提示词", "新增提示词"),
    (r"^PUT /api/prompts/[^/]+$", "update", "提示词", "编辑提示词"),
    (r"^DELETE /api/prompts/[^/]+$", "delete", "提示词", "删除提示词"),
    (r"^POST /api/api-test-cases$", "create", "接口用例", "新增接口用例"),
    (r"^PUT /api/api-test-cases/\d+$", "update", "接口用例", "编辑接口用例"),
    (r"^DELETE /api/api-test-cases/\d+$", "delete", "接口用例", "删除接口用例"),
    (r"^PATCH /api/subscriptions/\d+$", "update", "订阅", "更新日志订阅"),
    (r"^POST /api/settings/repo-access$", "update", "仓库访问", "更新仓库访问配置"),
]


def _match_api_audit(method: str, path: str) -> tuple[str, str, str] | None:
    signature = f"{method.upper()} {path}"
    for pattern, action, resource_type, content in _API_AUDIT_RULES:
        if re.match(pattern, signature):
            return action, resource_type, content
    return None


def record_operation(
    db: Session,
    *,
    user: User | None,
    action: str,
    content: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    extra: dict[str, Any] | None = None,
) -> OperationLog:
    log = OperationLog(
        user_id=user.id if user else None,
        username=(user.nickname or user.username) if user else "系统",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        content=content,
        ip_address=ip_address,
        extra=extra,
        created_at=datetime.utcnow(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def record_api_operation(
    db: Session,
    *,
    user: User | None,
    method: str,
    path: str,
    status_code: int,
    ip_address: str | None = None,
) -> None:
    if status_code >= 400:
        return
    if path.startswith("/api/auth") or path.startswith("/api/operation-logs") or path.startswith(
        "/api/users"
    ):
        return
    matched = _match_api_audit(method, path)
    if not matched:
        return
    action, resource_type, content = matched
    record_operation(
        db,
        user=user,
        action=action,
        content=content,
        resource_type=resource_type,
        ip_address=ip_address,
        extra={"method": method, "path": path},
    )


def record_page_open(
    db: Session,
    *,
    user: User,
    menu_key: str,
    ip_address: str | None = None,
) -> OperationLog:
    label = PAGE_LABELS.get(menu_key, menu_key)
    return record_operation(
        db,
        user=user,
        action="open",
        content=f"打开了{label}",
        resource_type="menu",
        resource_id=menu_key,
        ip_address=ip_address,
    )


def list_operation_logs(
    db: Session,
    *,
    keyword: str | None = None,
    action: str | None = None,
    username: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[OperationLog], int]:
    query = db.query(OperationLog)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                OperationLog.content.like(like),
                OperationLog.username.like(like),
                OperationLog.resource_type.like(like),
            )
        )
    if action:
        query = query.filter(OperationLog.action == action.strip())
    if username:
        query = query.filter(OperationLog.username.like(f"%{username.strip()}%"))
    total = query.count()
    rows = (
        query.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return rows, total

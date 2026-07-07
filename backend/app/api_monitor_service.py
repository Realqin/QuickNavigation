from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.api_monitor_diff import ApiEndpointChangeItem, diff_api_specs, summarize_api_changes
from app.api_monitor_spec_utils import (
    endpoint_key,
    expand_spec_for_read,
    iter_spec_endpoints,
    normalize_spec_for_storage,
)
from app.fastapi_scanner import build_spec, scan_fastapi_sources
from app.gateway_route_utils import apply_gateway_prefixes, discover_gateway_routes
from app.spring_java_models import JavaTypeResolver, list_git_tracked_files
from app.spring_scanner import scan_spring_sources
from app.models import ApiEndpointChange, ApiScanRun, ApiSnapshot, Connection, Subscription
from app.repo_access_config import get_gitlab_token
from app.repo_service import (
    normalize_git_clone_url,
    parse_gitlab_tree_branch,
    parse_repo_url,
    prepare_git_clone_url,
    verify_gitlab_repo_access,
)
from app.services import connection_is_gitlab_type, create_activity_log

logger = logging.getLogger(__name__)

SCAN_PATH_HINTS = ("app/routers", "app/router", "routers", "router", "api", "src/main", "backend/app")
JAVA_SCAN_HINTS = ("/controller/", "/endpoint/", "controller.java", "endpoint.java")
LOCAL_SCAN_ROOT = Path(__file__).resolve().parent
SAFE_KEY_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


def _optional_clone_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "none", "null"}:
        return ""
    return text


def _sanitize_git_error(text: str) -> str:
    cleaned = text
    token = get_gitlab_token()
    if token:
        cleaned = cleaned.replace(token, "****")
        cleaned = cleaned.replace(urllib.parse.quote(token, safe=""), "****")
    return cleaned.strip()


def _service_id(connection_id: int, link_key: str) -> str:
    return f"{connection_id}:{link_key}"


def _parse_service_id(service_id: str) -> tuple[int, str]:
    raw = service_id
    if "@" in service_id:
        raw = service_id.rsplit("@", 1)[0]
    if ":" not in raw:
        return int(raw), "main"
    connection_id_raw, link_key = raw.split(":", 1)
    return int(connection_id_raw), link_key or "main"


def _module_from_source_file(source_file: str) -> str | None:
    for part in source_file.replace("\\", "/").split("/"):
        if part.startswith("hscp-"):
            return part
    return None


def _discover_repo_modules(subscription_id: int, link_key: str) -> list[str]:
    cache_dir = _repo_cache_dir(subscription_id, link_key)
    if not cache_dir.is_dir():
        return []
    return sorted(
        item.name
        for item in cache_dir.iterdir()
        if item.is_dir() and item.name.startswith("hscp-")
    )


def _count_endpoints_by_module(spec: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not spec:
        return counts
    for endpoint in iter_spec_endpoints(spec):
        module = _module_from_source_file(str((endpoint.get("source") or {}).get("file") or ""))
        if not module:
            continue
        counts[module] = counts.get(module, 0) + 1
    return counts


def _filter_spec_by_module(spec: dict[str, Any], module: str) -> dict[str, Any]:
    filtered_groups: list[dict[str, Any]] = []
    for group in spec.get("groups") or []:
        endpoints = [
            endpoint
            for endpoint in group.get("endpoints") or []
            if _module_from_source_file(str((endpoint.get("source") or {}).get("file") or "")) == module
        ]
        if not endpoints:
            continue
        filtered_groups.append(
            {
                "tag": group.get("tag") or "default",
                "endpoints": endpoints,
            }
        )
    endpoint_count = sum(len(group.get("endpoints") or []) for group in filtered_groups)
    return {
        **spec,
        "groups": filtered_groups,
        "endpoint_count": endpoint_count,
    }


def _repo_cache_root() -> Path:
    return Path(settings.api_repo_cache_dir)


def _repo_cache_dir(subscription_id: int, link_key: str) -> Path:
    safe_key = SAFE_KEY_PATTERN.sub("_", link_key)
    return _repo_cache_root() / f"{subscription_id}_{safe_key}"


def resolve_link_target(conn: Connection, link_key: str) -> dict[str, str] | None:
    if link_key == "main":
        parsed = parse_gitlab_tree_branch(conn.url) or parse_repo_url(conn.url)
        if not parsed.repo_path and not conn.url.strip():
            return None
        return {
            "name": conn.name,
            "url": conn.url.strip(),
            "clone_url": _optional_clone_url(conn.host),
            "branch": (parsed.branch if parsed else None) or "main",
            "repo_path": (parsed.repo_path if parsed else "") or "",
        }

    sub_links = conn.sub_links or []
    if not link_key.startswith("sub:"):
        return None
    try:
        index = int(link_key.split(":", 1)[1])
    except (IndexError, ValueError):
        return None
    if index < 0 or index >= len(sub_links):
        return None
    item = sub_links[index]
    if not isinstance(item, dict):
        return None
    url = str(item.get("url") or "").strip()
    if not url:
        return None
    parsed = parse_gitlab_tree_branch(url) or parse_repo_url(url)
    return {
        "name": str(item.get("name") or f"子链接 {index + 1}").strip(),
        "url": url,
        "clone_url": _optional_clone_url(item.get("clone_url")),
        "branch": (parsed.branch if parsed else None) or "main",
        "repo_path": (parsed.repo_path if parsed else "") or "",
    }


def list_api_monitor_services(
    db: Session,
    *,
    project: int | None = None,
    environment: int | None = None,
    name: str | None = None,
) -> list[dict[str, Any]]:
    from app.services import FILTER_EMPTY, _json_contains, _json_is_empty, connection_environment_display, connection_project_display, get_dict_label_name

    services: list[dict[str, Any]] = []
    query = db.query(Connection).order_by(Connection.sort_order.asc(), Connection.id.asc())
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

    name_text = (name or "").strip()
    connections = query.all()
    # 批量预取所有相关订阅的 ApiSnapshot，避免循环内逐 subscription 查询
    gitlab_sub_ids = [
        conn.subscription.id
        for conn in connections
        if connection_is_gitlab_type(db, conn) and conn.subscription
    ]
    snapshot_rows = (
        db.query(ApiSnapshot).filter(ApiSnapshot.subscription_id.in_(gitlab_sub_ids)).all()
        if gitlab_sub_ids
        else []
    )
    snapshots_by_sub: dict[int, dict[str, Any]] = {}
    for row in snapshot_rows:
        snapshots_by_sub.setdefault(row.subscription_id, {})[row.link_key] = row

    for conn in connections:
        if not connection_is_gitlab_type(db, conn):
            continue
        sub = conn.subscription
        if not sub:
            continue
        link_enabled = sub.link_enabled or {}
        snapshot_by_key = snapshots_by_sub.get(sub.id, {})

        for link_key in ["main", *[f"sub:{index}" for index in range(len(conn.sub_links or []))]]:
            if not bool(link_enabled.get(link_key)):
                continue
            target = resolve_link_target(conn, link_key)
            if not target or not _optional_clone_url(target.get("clone_url")):
                continue
            snapshot = snapshot_by_key.get(link_key)
            endpoint_count = 0
            if snapshot and snapshot.spec:
                endpoint_count = int(snapshot.spec.get("endpoint_count") or 0)
            service = {
                "id": _service_id(conn.id, link_key),
                "connection_id": conn.id,
                "subscription_id": sub.id if sub else None,
                "link_key": link_key,
                "name": target["name"] if link_key != "main" else conn.name,
                "connection_name": conn.name,
                "repo_path": target["repo_path"],
                "branch": target["branch"],
                "projects": conn.projects or [],
                "environments": conn.environments or [],
            }
            if (
                name_text
                and service["id"] != name_text
                and _service_display_name(service) != name_text
            ):
                continue
            services.append(
                {
                    **service,
                    "project_display": connection_project_display(db, conn),
                    "environment_display": connection_environment_display(db, conn),
                    "connection_type_name": get_dict_label_name(db, conn.type),
                    "endpoint_count": endpoint_count,
                    "last_scan_at": snapshot.last_scan_at if snapshot else None,
                    "scan_status": snapshot.scan_status if snapshot else None,
                    "has_snapshot": bool(snapshot and snapshot.spec),
                }
            )
    return services


def _service_display_name(service: dict[str, Any]) -> str:
    connection_name = str(service["connection_name"]).strip()
    if service["link_key"] == "main":
        return connection_name
    child_name = str(service["name"]).strip()
    return f"{connection_name}/{child_name}"


def _get_service_context(
    db: Session,
    service_id: str,
    *,
    module: str | None = None,
) -> tuple[Connection, Subscription, ApiSnapshot, dict[str, Any]]:
    connection_id, link_key = _parse_service_id(service_id)
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise ValueError("连接不存在")
    if not connection_is_gitlab_type(db, conn):
        raise ValueError("仅支持 GitLab 类型连接")
    sub = conn.subscription
    if not sub:
        raise ValueError("该连接尚未建立订阅，请先在日志订阅中启用")
    snapshot = (
        db.query(ApiSnapshot)
        .filter(ApiSnapshot.subscription_id == sub.id, ApiSnapshot.link_key == link_key)
        .first()
    )
    if not snapshot:
        raise ValueError("尚未生成接口文档，请先在日志订阅中启用链接或点击「获取最新代码」")
    if not snapshot.spec:
        if snapshot.scan_status == "running":
            raise ValueError("接口文档正在生成中，请稍后刷新")
        if snapshot.scan_status == "failed":
            raise ValueError(snapshot.last_error or "接口扫描失败，请重新获取代码")
        raise ValueError("尚未生成接口文档，请先在日志订阅中启用链接或点击「获取最新代码」")
    spec = expand_spec_for_read(snapshot.spec)
    module_name = (module or "").strip()
    if module_name and module_name != "default":
        spec = _filter_spec_by_module(spec, module_name)
        if not iter_spec_endpoints(spec):
            raise ValueError(f"未找到服务：{module_name}")
    return conn, sub, snapshot, spec


def _find_endpoint_in_spec(spec: dict[str, Any], endpoint_id: str) -> dict[str, Any] | None:
    for endpoint in iter_spec_endpoints(spec):
        if endpoint_key(endpoint) == endpoint_id or endpoint.get("id") == endpoint_id:
            return endpoint
    return None


def _endpoint_summary(endpoint: dict[str, Any]) -> dict[str, Any]:
    source = endpoint.get("source") or {}
    summary = endpoint.get("summary") or endpoint.get("path") or ""
    author = source.get("author")
    if author:
        summary = f"{summary} · {author}"
    return {
        "id": endpoint.get("id") or "",
        "method": endpoint.get("method") or "",
        "path": endpoint.get("path") or "",
        "summary": summary,
    }


def list_api_monitor_filter_options(
    db: Session,
    *,
    project: int | None = None,
    environment: int | None = None,
) -> dict[str, Any]:
    from app.services import DICT_ENVIRONMENT, DICT_PROJECT, get_dict_item

    all_services = list_api_monitor_services(db)

    project_ids: set[int] = set()
    for service in all_services:
        for raw_id in service["projects"]:
            project_ids.add(int(raw_id))

    projects: list[dict[str, Any]] = []
    for project_id in sorted(project_ids):
        item = get_dict_item(db, project_id, DICT_PROJECT)
        projects.append({"id": project_id, "name": item.name if item else str(project_id)})

    scoped = all_services
    if project is not None:
        scoped = [service for service in all_services if project in service["projects"]]

    environment_ids: set[int] = set()
    for service in scoped:
        for raw_id in service["environments"]:
            environment_ids.add(int(raw_id))

    environments: list[dict[str, Any]] = []
    for environment_id in sorted(environment_ids):
        item = get_dict_item(db, environment_id, DICT_ENVIRONMENT)
        environments.append(
            {"id": environment_id, "name": item.name if item else str(environment_id)}
        )

    name_scope = scoped
    if environment is not None:
        name_scope = [service for service in scoped if environment in service["environments"]]

    names = sorted(
        [
            {"id": service["id"], "label": _service_display_name(service)}
            for service in name_scope
        ],
        key=lambda item: item["label"].lower(),
    )

    return {
        "projects": projects,
        "environments": environments,
        "names": names,
    }


def _should_scan_python_file(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/").lower()
    if not normalized.endswith(".py"):
        return False
    if any(part in normalized for part in ("/tests/", "/test/", "__pycache__", "/migrations/")):
        return False
    return any(hint in normalized for hint in SCAN_PATH_HINTS) or normalized.endswith("main.py")


def _should_scan_java_file(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/").lower()
    if not normalized.endswith(".java"):
        return False
    if any(part in normalized for part in ("/tests/", "/test/")):
        return False
    if "/src/main/java/" not in normalized:
        return False
    return any(hint in normalized for hint in JAVA_SCAN_HINTS)



def _collect_source_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    if not root.exists():
        return files

    tracked = list_git_tracked_files(root, "*.java", "*.py")
    if tracked is not None:
        rel_paths = tracked
    else:
        rel_paths = []
        for pattern in ("*.java", "*.py"):
            for path in root.rglob(pattern):
                if path.is_file():
                    rel_paths.append(path.relative_to(root).as_posix())

    for rel in rel_paths:
        if not (_should_scan_python_file(rel) or _should_scan_java_file(rel)):
            continue
        try:
            files[rel] = (root / rel).read_text(encoding="utf-8")
        except OSError:
            continue
    return files


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        detail = _sanitize_git_error((result.stderr or result.stdout or "git 命令执行失败").strip())
        lowered = detail.lower()
        if (
            "could not read username" in lowered
            or "authentication failed" in lowered
            or "access denied" in lowered
            or "invalid credentials" in lowered
            or "returned error: 401" in lowered
            or "returned error: 403" in lowered
        ):
            if not get_gitlab_token():
                raise RuntimeError(
                    "未配置 GitLab Token，请在「日志订阅 → 仓库访问配置」中填写 Token"
                )
            raise RuntimeError(
                "Git 拉取认证失败，请确认 GitLab Token 有效且具有该仓库的 read_repository 权限；"
                "也可在连接管理中填写 HTTPS Clone 地址后重试"
            )
        if "returned error: 404" in lowered or "repository not found" in lowered:
            raise RuntimeError("仓库不存在或无访问权限，请检查 Clone 地址与 Token 权限")
        if "returned error: 500" in lowered or "returned error: 502" in lowered:
            raise RuntimeError(
                "GitLab 服务器异常，无法拉取代码（HTTP 500/502）。"
                "请确认 Clone 地址、分支名称正确，Token 有效且有仓库读权限；"
                "也可在连接管理中直接填写 HTTPS Clone 地址后重试"
            )
        raise RuntimeError(detail)
    return (result.stdout or "").strip()


def _is_shallow_repo(cwd: Path) -> bool:
    try:
        return _run_git(["rev-parse", "--is-shallow-repository"], cwd=cwd).strip() == "true"
    except RuntimeError:
        return False


def _remote_branch_exists(cwd: Path, branch: str) -> bool:
    try:
        _run_git(["rev-parse", "--verify", f"origin/{branch}^{{commit}}"], cwd=cwd)
        return True
    except RuntimeError:
        return False


def _ensure_remote_branch(cwd: Path, branch: str) -> None:
    if _remote_branch_exists(cwd, branch):
        return

    fetch_args = ["fetch", "origin", f"{branch}:refs/remotes/origin/{branch}"]
    if _is_shallow_repo(cwd):
        fetch_args[1:1] = ["--depth", "1"]
    _run_git(fetch_args, cwd=cwd)


def _checkout_branch(cwd: Path, branch: str) -> None:
    _ensure_remote_branch(cwd, branch)
    try:
        _run_git(["checkout", branch], cwd=cwd)
    except RuntimeError:
        _run_git(["checkout", "-B", branch, f"origin/{branch}"], cwd=cwd)


def _clone_or_update_repo(clone_url: str, branch: str, target_dir: Path) -> str:
    verify_gitlab_repo_access(clone_url)
    effective_url = prepare_git_clone_url(clone_url)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists() and (target_dir / ".git").exists():
        _run_git(["remote", "set-url", "origin", effective_url], cwd=target_dir)
        _run_git(["fetch", "--all", "--prune"], cwd=target_dir)
        _checkout_branch(target_dir, branch)
        _run_git(["pull", "--ff-only", "origin", branch], cwd=target_dir)
    else:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        try:
            _run_git(
                ["clone", "--depth", "1", "--branch", branch, effective_url, str(target_dir)],
            )
        except RuntimeError:
            _run_git(["clone", "--depth", "1", effective_url, str(target_dir)])
            _checkout_branch(target_dir, branch)
    return _run_git(["rev-parse", "HEAD"], cwd=target_dir)


def _get_latest_commit_message(cwd: Path) -> str:
    try:
        return _run_git(["log", "-1", "--format=%s"], cwd=cwd)
    except RuntimeError:
        return ""


def _snapshot_hash(spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scan_local_tree(root: Path, *, meta: dict[str, Any]) -> dict[str, Any]:
    import time

    started = time.perf_counter()
    files = _collect_source_files(root)
    java_files = {path: source for path, source in files.items() if path.endswith(".java")}
    java_resolver = JavaTypeResolver.from_repo_root(root, inline_sources=java_files)
    resolver_ms = int((time.perf_counter() - started) * 1000)

    scan_started = time.perf_counter()
    python_files = {path: source for path, source in files.items() if path.endswith(".py")}
    endpoints = scan_fastapi_sources(python_files) + scan_spring_sources(
        java_files,
        resolver=java_resolver,
    )
    gateway_routes = discover_gateway_routes(root)
    if gateway_routes:
        endpoints = apply_gateway_prefixes(endpoints, gateway_routes)
        logger.info("Applied gateway prefixes from %d route entries", len(gateway_routes))
    scan_ms = int((time.perf_counter() - scan_started) * 1000)
    logger.info(
        "API scan finished: resolver=%dms warmed_types=%d paths=%d scan=%dms endpoints=%d",
        resolver_ms,
        len(java_resolver.type_index),
        java_resolver.path_index_count,
        scan_ms,
        len(endpoints),
    )
    scanners: list[str] = []
    if python_files:
        scanners.append("fastapi@v1")
    if java_files:
        scanners.append("spring@v1")
    return build_spec(
        endpoints,
        meta={
            **meta,
            "scanned_at": datetime.utcnow().isoformat(),
            "scanner": "+".join(scanners) if scanners else "none",
            "scanned_files": sorted(files.keys()),
            "python_file_count": len(python_files),
            "java_file_count": len(java_files),
            "java_path_index_count": java_resolver.path_index_count,
            "java_type_count": len(java_resolver.type_index),
            "scan_resolver_ms": resolver_ms,
            "scan_parse_ms": scan_ms,
        },
    )


def _iter_connection_link_keys(conn: Connection) -> list[str]:
    keys = ["main"]
    keys.extend(f"sub:{index}" for index in range(len(conn.sub_links or [])))
    return keys


def _link_has_clone_url(conn: Connection, link_key: str) -> bool:
    target = resolve_link_target(conn, link_key)
    return bool(target and _optional_clone_url(target.get("clone_url")))


def _persist_scan_run(
    db: Session,
    *,
    snapshot_row: ApiSnapshot,
    subscription_id: int,
    link_key: str,
    branch: str | None,
    commit_sha: str,
    commit_message: str,
    is_baseline: bool,
    endpoint_count_before: int,
    endpoint_count_after: int,
    changes: list[ApiEndpointChangeItem],
) -> ApiScanRun:
    added_count = sum(1 for item in changes if item.change_type == "added")
    modified_count = sum(1 for item in changes if item.change_type == "modified")
    removed_count = sum(1 for item in changes if item.change_type == "removed")
    scan_run = ApiScanRun(
        snapshot_id=snapshot_row.id,
        subscription_id=subscription_id,
        link_key=link_key,
        commit_sha=commit_sha,
        commit_message=commit_message or None,
        branch=branch,
        is_baseline=is_baseline,
        endpoint_count_before=endpoint_count_before,
        endpoint_count_after=endpoint_count_after,
        added_count=added_count,
        modified_count=modified_count,
        removed_count=removed_count,
        scanned_at=datetime.utcnow(),
    )
    db.add(scan_run)
    db.flush()

    for change in changes:
        db.add(
            ApiEndpointChange(
                scan_run_id=scan_run.id,
                subscription_id=subscription_id,
                link_key=link_key,
                endpoint_key=change.endpoint_key,
                change_type=change.change_type,
                tag=change.tag,
                summary=change.summary,
                before_json=change.before,
                after_json=change.after,
                diff_json=change.diff or None,
                source_file=change.source_file or None,
                source_line=change.source_line,
            )
        )
    return scan_run


def _emit_api_monitor_changes(
    db: Session,
    *,
    sub: Subscription,
    conn: Connection,
    target_name: str,
    link_key: str,
    branch: str | None,
    commit_sha: str,
    scan_run: ApiScanRun,
    changes: list[ApiEndpointChangeItem],
) -> None:
    if not changes:
        return

    from app.services import _primary_project_environment

    project, environment = _primary_project_environment(db, conn)
    create_activity_log(
        db,
        subscription_id=sub.id,
        connection_id=conn.id,
        project=project,
        environment=environment,
        source_type="api-monitor",
        title=f"接口变更 · {target_name}",
        summary=summarize_api_changes(changes),
        payload={
            "event": "api_change",
            "link_key": link_key,
            "branch": branch,
            "commit_sha": commit_sha,
            "scan_run_id": scan_run.id,
            "added_count": scan_run.added_count,
            "modified_count": scan_run.modified_count,
            "removed_count": scan_run.removed_count,
            "endpoint_count_before": scan_run.endpoint_count_before,
            "endpoint_count_after": scan_run.endpoint_count_after,
            "changes": [
                {
                    "endpoint_key": item.endpoint_key,
                    "change_type": item.change_type,
                    "tag": item.tag,
                    "summary": item.summary,
                }
                for item in changes[:50]
            ],
        },
        author="api-monitor",
    )


def sync_api_monitor_link(
    db: Session,
    *,
    subscription_id: int,
    link_key: str,
    baseline_only: bool = False,
    require_enabled: bool = True,
) -> dict[str, Any]:
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub or not sub.connection:
        raise ValueError("订阅不存在")
    conn = sub.connection
    if not connection_is_gitlab_type(db, conn):
        raise ValueError("仅支持 GitLab 类型连接")

    link_enabled = sub.link_enabled or {}
    if require_enabled and not bool(link_enabled.get(link_key)):
        raise ValueError("请先在订阅列表中启用该链接")

    target = resolve_link_target(conn, link_key)
    if not target:
        raise ValueError("无法解析仓库地址，请确认连接 URL 配置正确")
    clone_url = _optional_clone_url(target.get("clone_url"))
    if not clone_url:
        raise ValueError("未配置 Clone 地址，无法拉取代码（可在连接管理中补充）")

    snapshot_row = (
        db.query(ApiSnapshot)
        .filter(ApiSnapshot.subscription_id == subscription_id, ApiSnapshot.link_key == link_key)
        .first()
    )
    if not snapshot_row:
        snapshot_row = ApiSnapshot(subscription_id=subscription_id, link_key=link_key)
        db.add(snapshot_row)

    snapshot_row.scan_status = "running"
    snapshot_row.last_error = None
    db.commit()

    cache_dir = _repo_cache_dir(subscription_id, link_key)
    try:
        commit_sha = _clone_or_update_repo(clone_url, target["branch"], cache_dir)
        commit_message = _get_latest_commit_message(cache_dir)
        spec = normalize_spec_for_storage(
            _scan_local_tree(
                cache_dir,
                meta={
                    "source": "git-clone",
                    "service_id": _service_id(conn.id, link_key),
                    "service_name": target["name"],
                    "connection_id": conn.id,
                    "subscription_id": subscription_id,
                    "link_key": link_key,
                    "repo_path": target["repo_path"],
                    "branch": target["branch"],
                    "clone_url": target["clone_url"],
                    "commit_sha": commit_sha,
                },
            )
        )
        had_baseline = bool(snapshot_row.spec)
        old_spec = snapshot_row.spec
        old_count = int((old_spec or {}).get("endpoint_count") or len(iter_spec_endpoints(old_spec)))
        new_count = int(spec.get("endpoint_count") or 0)

        changes: list[ApiEndpointChangeItem] = []
        if had_baseline and not baseline_only:
            changes = diff_api_specs(old_spec, spec)

        snapshot_row.spec = spec
        snapshot_row.snapshot_hash = _snapshot_hash(spec)
        snapshot_row.commit_sha = commit_sha
        snapshot_row.last_scan_at = datetime.utcnow()
        snapshot_row.last_error = None
        snapshot_row.scan_status = "completed"
        db.flush()

        scan_run = _persist_scan_run(
            db,
            snapshot_row=snapshot_row,
            subscription_id=subscription_id,
            link_key=link_key,
            branch=target["branch"],
            commit_sha=commit_sha,
            commit_message=commit_message,
            is_baseline=not had_baseline,
            endpoint_count_before=old_count,
            endpoint_count_after=new_count,
            changes=changes if had_baseline and not baseline_only else [],
        )
        db.commit()
        db.refresh(snapshot_row)

        from app.services import _primary_project_environment

        project, environment = _primary_project_environment(db, conn)
        if not had_baseline:
            create_activity_log(
                db,
                subscription_id=sub.id,
                connection_id=conn.id,
                project=project,
                environment=environment,
                source_type="api-monitor",
                title=f"接口基线已建立：{target['name']}",
                summary=f"共扫描到 {new_count} 个接口",
                payload={
                    "event": "api_baseline",
                    "link_key": link_key,
                    "endpoint_count": new_count,
                    "branch": target["branch"],
                    "commit_sha": commit_sha,
                    "scan_run_id": scan_run.id,
                },
                author="api-monitor",
            )
            db.commit()
        elif not baseline_only:
            _emit_api_monitor_changes(
                db,
                sub=sub,
                conn=conn,
                target_name=target["name"],
                link_key=link_key,
                branch=target["branch"],
                commit_sha=commit_sha,
                scan_run=scan_run,
                changes=changes,
            )
            if changes:
                db.commit()

        return {
            "subscription_id": subscription_id,
            "link_key": link_key,
            "endpoint_count": new_count,
            "commit_sha": commit_sha,
            "was_first_scan": not had_baseline,
            "changes_detected": len(changes),
            "scan_run_id": scan_run.id,
            "snapshot": snapshot_row,
        }
    except Exception as exc:
        logger.exception("API monitor sync failed for subscription %s link %s", subscription_id, link_key)
        snapshot_row.scan_status = "failed"
        snapshot_row.last_error = str(exc)
        snapshot_row.last_scan_at = datetime.utcnow()
        db.commit()
        raise


def get_api_monitor_spec(db: Session, service_id: str, *, module: str | None = None) -> dict[str, Any]:
    _, _, _, spec = _get_service_context(db, service_id, module=module)
    return expand_spec_for_read(spec)


def list_api_monitor_modules(db: Session, service_id: str) -> dict[str, Any]:
    conn, sub, snapshot, spec = _get_service_context(db, service_id)
    _, link_key = _parse_service_id(service_id)
    endpoint_counts = _count_endpoints_by_module(snapshot.spec if snapshot and snapshot.spec else None)
    module_names = _discover_repo_modules(sub.id, link_key)
    if not module_names:
        module_names = sorted(endpoint_counts.keys())
    modules = [
        {
            "name": name,
            "endpoint_count": endpoint_counts.get(name, 0),
        }
        for name in module_names
    ]
    if not modules and spec:
        modules = [
            {
                "name": "default",
                "endpoint_count": int(spec.get("endpoint_count") or 0),
            }
        ]
    return {
        "service_id": service_id,
        "modules": modules,
    }


def _collect_removed_endpoint_keys(
    db: Session,
    *,
    subscription_id: int,
    link_key: str,
) -> set[str]:
    """Return endpoint keys whose latest scan change is ``removed``."""
    rows = (
        db.query(
            ApiEndpointChange.endpoint_key,
            ApiEndpointChange.change_type,
            ApiScanRun.scanned_at,
            ApiEndpointChange.id,
        )
        .join(ApiScanRun, ApiScanRun.id == ApiEndpointChange.scan_run_id)
        .filter(
            ApiEndpointChange.subscription_id == subscription_id,
            ApiEndpointChange.link_key == link_key,
        )
        .order_by(ApiScanRun.scanned_at.asc(), ApiEndpointChange.id.asc())
        .all()
    )
    latest_state: dict[str, str] = {}
    for endpoint_key_val, change_type, _scanned_at, _change_id in rows:
        latest_state[str(endpoint_key_val)] = str(change_type)
    return {key for key, change_type in latest_state.items() if change_type == "removed"}


def get_api_monitor_groups(db: Session, service_id: str, *, module: str | None = None) -> dict[str, Any]:
    from app.services import connection_environment_display, connection_project_display

    conn, sub, snapshot, spec = _get_service_context(db, service_id, module=module)
    _, link_key = _parse_service_id(service_id)
    removed_endpoint_keys = sorted(
        _collect_removed_endpoint_keys(
            db,
            subscription_id=sub.id,
            link_key=link_key,
        )
    )
    target = resolve_link_target(conn, link_key)
    service = {
        "id": service_id,
        "link_key": link_key,
        "name": target["name"] if target else conn.name,
        "connection_name": conn.name,
        "repo_path": target["repo_path"] if target else "",
        "branch": target["branch"] if target else None,
    }
    groups = [
        {
            "tag": str(group.get("tag") or "default"),
            "endpoint_count": len(group.get("endpoints") or []),
        }
        for group in spec.get("groups") or []
    ]
    return {
        "service_id": service_id,
        "module": (module or "").strip() or None,
        "display_name": _service_display_name(service),
        "endpoint_count": int(spec.get("endpoint_count") or 0),
        "has_snapshot": True,
        "scan_status": snapshot.scan_status,
        "repo_path": service["repo_path"],
        "branch": service["branch"],
        "project_display": connection_project_display(db, conn),
        "environment_display": connection_environment_display(db, conn),
        "groups": groups,
        "removed_endpoint_keys": removed_endpoint_keys,
    }


def get_api_monitor_group_endpoints(
    db: Session,
    service_id: str,
    tag: str,
    *,
    module: str | None = None,
) -> dict[str, Any]:
    _, _, _, spec = _get_service_context(db, service_id, module=module)
    normalized_tag = (tag or "").strip()
    for group in spec.get("groups") or []:
        if str(group.get("tag") or "default") != normalized_tag:
            continue
        endpoints = [_endpoint_summary(endpoint) for endpoint in group.get("endpoints") or []]
        endpoints.sort(key=lambda item: (item["path"], item["method"]))
        return {"tag": normalized_tag, "endpoints": endpoints}
    raise ValueError(f"未找到服务分类：{normalized_tag}")


def get_api_monitor_endpoint(db: Session, service_id: str, endpoint_id: str) -> dict[str, Any]:
    _, _, _, spec = _get_service_context(db, service_id)
    endpoint = _find_endpoint_in_spec(spec, endpoint_id)
    if not endpoint:
        raise ValueError("接口不存在")
    return endpoint


def _scan_run_to_dict(scan_run: ApiScanRun) -> dict[str, Any]:
    return {
        "id": scan_run.id,
        "subscription_id": scan_run.subscription_id,
        "link_key": scan_run.link_key,
        "commit_sha": scan_run.commit_sha,
        "commit_message": scan_run.commit_message,
        "branch": scan_run.branch,
        "is_baseline": scan_run.is_baseline,
        "endpoint_count_before": scan_run.endpoint_count_before,
        "endpoint_count_after": scan_run.endpoint_count_after,
        "added_count": scan_run.added_count,
        "modified_count": scan_run.modified_count,
        "removed_count": scan_run.removed_count,
        "scanned_at": scan_run.scanned_at,
    }


def _endpoint_change_to_dict(change: ApiEndpointChange, *, include_detail: bool = False) -> dict[str, Any]:
    data = {
        "id": change.id,
        "scan_run_id": change.scan_run_id,
        "endpoint_key": change.endpoint_key,
        "change_type": change.change_type,
        "tag": change.tag,
        "summary": change.summary,
        "source_file": change.source_file,
        "source_line": change.source_line,
        "created_at": change.created_at,
    }
    if include_detail:
        data.update(
            {
                "before_json": change.before_json,
                "after_json": change.after_json,
                "diff_json": change.diff_json,
            }
        )
    return data


def list_api_monitor_scan_runs(
    db: Session,
    service_id: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    _, _, snapshot, _ = _get_service_context(db, service_id)
    rows = (
        db.query(ApiScanRun)
        .filter(ApiScanRun.snapshot_id == snapshot.id)
        .order_by(ApiScanRun.scanned_at.desc())
        .limit(limit)
        .all()
    )
    return [_scan_run_to_dict(row) for row in rows]


def list_api_monitor_scan_run_changes(
    db: Session,
    service_id: str,
    scan_run_id: int,
) -> dict[str, Any]:
    _, _, snapshot, _ = _get_service_context(db, service_id)
    scan_run = (
        db.query(ApiScanRun)
        .filter(ApiScanRun.id == scan_run_id, ApiScanRun.snapshot_id == snapshot.id)
        .first()
    )
    if not scan_run:
        raise ValueError("扫描记录不存在")
    changes = (
        db.query(ApiEndpointChange)
        .filter(ApiEndpointChange.scan_run_id == scan_run.id)
        .order_by(ApiEndpointChange.id.asc())
        .all()
    )
    return {
        "scan_run": _scan_run_to_dict(scan_run),
        "changes": [_endpoint_change_to_dict(item, include_detail=True) for item in changes],
    }


def list_api_monitor_endpoint_changes(
    db: Session,
    service_id: str,
    endpoint_id: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    _, sub, snapshot, _ = _get_service_context(db, service_id)
    _, link_key = _parse_service_id(service_id)
    normalized_endpoint_id = (endpoint_id or "").strip()
    rows = (
        db.query(ApiEndpointChange, ApiScanRun)
        .join(ApiScanRun, ApiScanRun.id == ApiEndpointChange.scan_run_id)
        .filter(
            ApiEndpointChange.subscription_id == sub.id,
            ApiEndpointChange.link_key == link_key,
            ApiEndpointChange.endpoint_key == normalized_endpoint_id,
        )
        .order_by(ApiScanRun.scanned_at.desc(), ApiEndpointChange.id.desc())
        .limit(limit)
        .all()
    )
    result: list[dict[str, Any]] = []
    for change, scan_run in rows:
        item = _endpoint_change_to_dict(change, include_detail=True)
        item["scan_run"] = _scan_run_to_dict(scan_run)
        result.append(item)
    return result


_API_MONITOR_SYNC_SEMAPHORE: asyncio.Semaphore | None = None
_API_MONITOR_SYNC_CONCURRENCY = 3


def _get_api_monitor_sync_semaphore() -> asyncio.Semaphore:
    global _API_MONITOR_SYNC_SEMAPHORE
    if _API_MONITOR_SYNC_SEMAPHORE is None:
        _API_MONITOR_SYNC_SEMAPHORE = asyncio.Semaphore(_API_MONITOR_SYNC_CONCURRENCY)
    return _API_MONITOR_SYNC_SEMAPHORE


async def sync_api_monitor_link_async(
    subscription_id: int,
    link_key: str,
    *,
    baseline_only: bool = False,
) -> None:
    async with _get_api_monitor_sync_semaphore():
        def _run() -> None:
            db = SessionLocal()
            try:
                sync_api_monitor_link(
                    db,
                    subscription_id=subscription_id,
                    link_key=link_key,
                    baseline_only=baseline_only,
                )
            except Exception:
                logger.exception("Async API monitor sync failed")
            finally:
                db.close()

        await asyncio.to_thread(_run)


def schedule_api_monitor_sync(subscription_id: int, link_key: str, *, baseline_only: bool = False) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        sync_api_monitor_link_async(
            subscription_id,
            link_key,
            baseline_only=baseline_only,
        )
    )


async def sync_subscription_api_links(
    db: Session,
    sub: Subscription,
    *,
    link_key: str | None = None,
) -> dict[str, Any]:
    if not sub.connection or not connection_is_gitlab_type(db, sub.connection):
        raise ValueError("仅支持 GitLab 类型连接")

    conn = sub.connection
    candidates = [link_key] if link_key else _iter_connection_link_keys(conn)
    syncable = [key for key in candidates if _link_has_clone_url(conn, key)]
    skipped = len(candidates) - len(syncable)

    if not syncable:
        raise ValueError("没有配置 Clone 地址的链接，无法拉取代码")

    subscription_id = sub.id

    def _run_one(key: str) -> dict[str, Any]:
        from app.database import SessionLocal

        thread_db = SessionLocal()
        try:
            return sync_api_monitor_link(
                thread_db,
                subscription_id=subscription_id,
                link_key=key,
                baseline_only=False,
                require_enabled=False,
            )
        finally:
            thread_db.close()

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for key in syncable:
        try:
            result = await asyncio.to_thread(_run_one, key)
            results.append(result)
        except Exception as exc:
            logger.exception("API monitor sync failed for subscription %s link %s", sub.id, key)
            errors.append({"link_key": key, "error": _sanitize_git_error(str(exc))})

    if not results:
        raise ValueError(errors[0]["error"] if errors else "接口文档同步失败")

    message = f"已同步 {len(results)} 个链接的接口文档"
    if skipped:
        message += f"，跳过 {skipped} 个未配置 Clone 的链接"
    if errors:
        message += f"，{len(errors)} 个失败"

    return {
        "subscription_id": sub.id,
        "synced": len(results),
        "skipped": skipped,
        "failed": len(errors),
        "message": message,
        "results": results,
        "errors": errors,
    }


_ALLOWED_PROXY_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_SKIP_PROXY_HEADERS = frozenset(
    {
        "host",
        "connection",
        "content-length",
        "transfer-encoding",
        "upgrade",
        "proxy-authorization",
        "proxy-connection",
    }
)


def _normalize_proxy_headers(headers: dict[str, str] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key).strip()
        if not name:
            continue
        if name.lower() in _SKIP_PROXY_HEADERS:
            continue
        normalized[name] = str(value)
    return normalized


async def proxy_api_monitor_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    import time
    from urllib.parse import urlparse

    import httpx

    normalized_method = (method or "GET").strip().upper()
    if normalized_method not in _ALLOWED_PROXY_METHODS:
        raise ValueError(f"不支持的请求方法：{normalized_method}")

    target = (url or "").strip()
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("仅支持 http/https 完整地址")

    from app.ssrf_guard import assert_safe_url, SsrfViolation

    try:
        assert_safe_url(target)
    except SsrfViolation as exc:
        raise ValueError(str(exc)) from exc

    request_headers = _normalize_proxy_headers(headers)
    started = time.perf_counter()
    try:
        # 禁用 follow_redirects，避免重定向绕过 SSRF 校验
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            response = await client.request(
                normalized_method,
                target,
                headers=request_headers,
                content=body if body not in (None, "") else None,
            )
    except httpx.RequestError as exc:
        raise ValueError(f"请求目标服务失败：{exc}") from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in _SKIP_PROXY_HEADERS
    }
    return {
        "status_code": response.status_code,
        "headers": response_headers,
        "body": response.text,
        "elapsed_ms": elapsed_ms,
    }

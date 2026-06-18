from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.api_monitor_spec_utils import endpoint_key, endpoint_tag, iter_spec_endpoints


@dataclass
class ApiEndpointChangeItem:
    change_type: str
    endpoint_key: str
    tag: str
    summary: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    diff: dict[str, Any] = field(default_factory=dict)
    source_file: str = ""
    source_line: int | None = None


def _canonical_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": endpoint.get("method"),
        "path": endpoint.get("path"),
        "summary": endpoint.get("summary"),
        "tags": endpoint.get("tags") or [],
        "request_content_type": endpoint.get("request_content_type"),
        "response_content_type": endpoint.get("response_content_type"),
        "parameters": endpoint.get("parameters") or [],
        "responses": endpoint.get("responses") or [],
    }


def endpoint_fingerprint(endpoint: dict[str, Any]) -> str:
    payload = json.dumps(_canonical_endpoint(endpoint), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _param_identity(param: dict[str, Any]) -> str:
    return f"{param.get('in')}:{param.get('name')}"


def _diff_parameters(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    before_map = {_param_identity(item): item for item in before}
    after_map = {_param_identity(item): item for item in after}
    added = [after_map[key] for key in sorted(set(after_map) - set(before_map))]
    removed = [before_map[key] for key in sorted(set(before_map) - set(after_map))]
    modified: list[dict[str, Any]] = []
    for key in sorted(set(before_map) & set(after_map)):
        if json.dumps(before_map[key], ensure_ascii=False, sort_keys=True) != json.dumps(
            after_map[key], ensure_ascii=False, sort_keys=True
        ):
            modified.append(
                {
                    "name": before_map[key].get("name"),
                    "in": before_map[key].get("in"),
                    "before": before_map[key],
                    "after": after_map[key],
                }
            )
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
    }


def _build_modified_summary(diff: dict[str, Any]) -> str:
    parts: list[str] = []
    if diff.get("summary_changed"):
        parts.append("摘要变更")
    param_diff = diff.get("parameters") or {}
    if param_diff.get("added"):
        parts.append(f"新增 {len(param_diff['added'])} 个参数")
    if param_diff.get("removed"):
        parts.append(f"删除 {len(param_diff['removed'])} 个参数")
    if param_diff.get("modified"):
        parts.append(f"修改 {len(param_diff['modified'])} 个参数")
    if diff.get("responses_changed"):
        parts.append("响应变更")
    if diff.get("request_content_type_changed"):
        parts.append("请求类型变更")
    if diff.get("response_content_type_changed"):
        parts.append("响应类型变更")
    return "；".join(parts) or "接口定义变更"


def _build_endpoint_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    if before.get("summary") != after.get("summary"):
        diff["summary_changed"] = {
            "before": before.get("summary"),
            "after": after.get("summary"),
        }
    if before.get("request_content_type") != after.get("request_content_type"):
        diff["request_content_type_changed"] = True
    if before.get("response_content_type") != after.get("response_content_type"):
        diff["response_content_type_changed"] = True
    param_diff = _diff_parameters(before.get("parameters") or [], after.get("parameters") or [])
    if param_diff["added"] or param_diff["removed"] or param_diff["modified"]:
        diff["parameters"] = param_diff
    if json.dumps(before.get("responses") or [], ensure_ascii=False, sort_keys=True) != json.dumps(
        after.get("responses") or [], ensure_ascii=False, sort_keys=True
    ):
        diff["responses_changed"] = True
    return diff


def _source_meta(endpoint: dict[str, Any] | None) -> tuple[str, int | None]:
    if not endpoint:
        return "", None
    source = endpoint.get("source") or {}
    file_path = str(source.get("file") or "")
    line = source.get("line")
    return file_path, int(line) if isinstance(line, int) else None


def diff_api_specs(old: dict[str, Any] | None, new: dict[str, Any]) -> list[ApiEndpointChangeItem]:
    if not old:
        return []

    old_map = {endpoint_key(item): item for item in iter_spec_endpoints(old)}
    new_map = {endpoint_key(item): item for item in iter_spec_endpoints(new)}
    changes: list[ApiEndpointChangeItem] = []

    for key in sorted(set(new_map) - set(old_map)):
        endpoint = new_map[key]
        source_file, source_line = _source_meta(endpoint)
        changes.append(
            ApiEndpointChangeItem(
                change_type="added",
                endpoint_key=key,
                tag=endpoint_tag(endpoint),
                summary=f"新增接口 {key}",
                after=_canonical_endpoint(endpoint),
                source_file=source_file,
                source_line=source_line,
            )
        )

    for key in sorted(set(old_map) - set(new_map)):
        endpoint = old_map[key]
        source_file, source_line = _source_meta(endpoint)
        changes.append(
            ApiEndpointChangeItem(
                change_type="removed",
                endpoint_key=key,
                tag=endpoint_tag(endpoint),
                summary=f"删除接口 {key}",
                before=_canonical_endpoint(endpoint),
                source_file=source_file,
                source_line=source_line,
            )
        )

    for key in sorted(set(old_map) & set(new_map)):
        before = old_map[key]
        after = new_map[key]
        if endpoint_fingerprint(before) == endpoint_fingerprint(after):
            continue
        diff = _build_endpoint_diff(before, after)
        source_file, source_line = _source_meta(after)
        changes.append(
            ApiEndpointChangeItem(
                change_type="modified",
                endpoint_key=key,
                tag=endpoint_tag(after),
                summary=f"{key}：{_build_modified_summary(diff)}",
                before=_canonical_endpoint(before),
                after=_canonical_endpoint(after),
                diff=diff,
                source_file=source_file,
                source_line=source_line,
            )
        )

    return changes


def summarize_api_changes(changes: list[ApiEndpointChangeItem]) -> str:
    if not changes:
        return "无接口变更"
    added = sum(1 for item in changes if item.change_type == "added")
    removed = sum(1 for item in changes if item.change_type == "removed")
    modified = sum(1 for item in changes if item.change_type == "modified")
    parts: list[str] = []
    if added:
        parts.append(f"新增 {added}")
    if removed:
        parts.append(f"删除 {removed}")
    if modified:
        parts.append(f"修改 {modified}")
    preview = "；".join(item.summary for item in changes[:4])
    if len(changes) > 4:
        preview += f"；等共 {len(changes)} 项"
    return f"{' / '.join(parts)} · {preview}"

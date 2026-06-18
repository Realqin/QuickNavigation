from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.code_diff_utils import AfterCodeLine, ParsedFileDiff, code_block_lang, parse_unified_diff
from app.llm_client import call_chat_completion, extract_test_cases_payload, suggest_output_tokens
from app.llm_config_service import get_active_llm_config

logger = logging.getLogger(__name__)

CODE_COMMENT_SYSTEM_PROMPT = (
    "你是代码讲解专家。用户会提供一次提交中「修改后」的完整代码片段（与 diff 完全一致）。"
    "你必须为每一行非空代码写中文说明，包括 kind=context 的上下文行、kind=added 的新增行、kind=modified 的修改行。"
    "只输出 JSON 对象，不要 Markdown。"
    "结构："
    '{"files":[{"path":"文件路径","comments":["与 lines 等长的说明数组"],'
    '"logic_before":"修改前整体逻辑","logic_after":"修改后整体逻辑","logic_diff":"核心差异"}]}'
    "规则："
    "1. comments 数组长度必须等于输入 lines 数组长度；"
    "2. 空行 code 的 comment 必须是 \"\"；"
    "3. 任意非空 code 的 comment 不得为空字符串，必须解释该行代码含义；"
    "4. context 行也要注释，说明该行在函数/模块中的作用；"
    "5. modified 行要点明相对 old_code 的变化；added 行说明新增作用；"
    "6. 不要出现「备注」二字，不要加 // 或 # 前缀；"
    "7. 每条 comment 不超过 40 字。"
)

CODE_COMMENT_FILL_PROMPT = (
    "你是代码讲解专家。以下代码行缺少 comment，请仅返回 JSON："
    '{"comments":[{"index":0,"comment":"..."}]}'
    "index 对应输入 lines 的 index；每条 comment 不得为空；不要 Markdown。"
)


def _serialize_lines(lines: list[AfterCodeLine]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        item: dict[str, Any] = {
            "index": index,
            "code": line.code,
            "kind": line.kind,
        }
        if line.kind == "modified" and line.old_code is not None:
            item["old_code"] = line.old_code
        payload.append(item)
    return payload


def _build_comment_request(files: list[ParsedFileDiff]) -> str:
    payload = {
        "files": [
            {
                "path": item.display_path,
                "lines": _serialize_lines(item.after_code_lines),
            }
            for item in files
        ]
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_comments(raw: object, expected_len: int) -> list[str]:
    if not isinstance(raw, list):
        return [""] * expected_len
    comments = [str(item).strip() for item in raw]
    if len(comments) < expected_len:
        comments.extend([""] * (expected_len - len(comments)))
    return comments[:expected_len]


def _fallback_comment(line: AfterCodeLine) -> str:
    code = line.code.strip()
    if line.kind == "modified":
        return "相对修改前，本行逻辑或实现有调整"
    if line.kind == "added":
        return "本次提交新增的代码"
    if len(code) > 36:
        return f"上下文：{code[:33]}…"
    return f"上下文：{code}"


def _ensure_line_comments(lines: list[AfterCodeLine], comments: list[str]) -> list[str]:
    ensured = list(comments)
    if len(ensured) < len(lines):
        ensured.extend([""] * (len(lines) - len(ensured)))
    for index, line in enumerate(lines):
        if not line.code.strip():
            ensured[index] = ""
            continue
        if not str(ensured[index] or "").strip():
            ensured[index] = _fallback_comment(line)
    return ensured[: len(lines)]


def _missing_comment_indices(lines: list[AfterCodeLine], comments: list[str]) -> list[int]:
    missing: list[int] = []
    for index, line in enumerate(lines):
        if not line.code.strip():
            continue
        comment = comments[index].strip() if index < len(comments) else ""
        if not comment:
            missing.append(index)
    return missing


async def _fill_missing_comments(
    *,
    llm_config: Any,
    lines: list[AfterCodeLine],
    comments: list[str],
    path: str,
) -> list[str]:
    missing = _missing_comment_indices(lines, comments)
    if not missing:
        return comments

    payload = {
        "path": path,
        "lines": [
            {
                "index": index,
                "code": lines[index].code,
                "kind": lines[index].kind,
                **(
                    {"old_code": lines[index].old_code}
                    if lines[index].kind == "modified" and lines[index].old_code is not None
                    else {}
                ),
            }
            for index in missing
        ],
    }
    user_content = json.dumps(payload, ensure_ascii=False, indent=2)
    output_budget = suggest_output_tokens(llm_config.context_limit, cap=4096, ratio=0.2, floor=800)
    result = await call_chat_completion(
        api_url=llm_config.api_url,
        api_key=llm_config.api_key,
        model_name=llm_config.model_name,
        messages=[
            {"role": "system", "content": CODE_COMMENT_FILL_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        max_tokens=output_budget,
        timeout=90.0,
        context_limit=llm_config.context_limit,
        response_format={"type": "json_object"},
    )
    try:
        parsed = extract_test_cases_payload(result.get("content"), result.get("full_text"))
    except ValueError:
        return comments

    filled = list(comments)
    items = parsed.get("comments")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            comment = str(item.get("comment") or "").strip()
            if isinstance(index, int) and 0 <= index < len(filled) and comment:
                filled[index] = comment
    return filled


def _build_line_blocks(lines: list[AfterCodeLine], comments: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line.code.strip():
            blocks.append({"type": "blank", "code": line.code})
            continue

        comment = comments[index] if index < len(comments) else ""
        if line.kind == "modified" and line.old_code is not None:
            blocks.append(
                {
                    "type": "changed",
                    "code": line.code,
                    "old_code": line.old_code,
                    "comment": comment,
                }
            )
        elif line.kind == "added":
            blocks.append(
                {
                    "type": "added",
                    "code": line.code,
                    "comment": comment,
                }
            )
        else:
            blocks.append(
                {
                    "type": "plain",
                    "code": line.code,
                    "comment": comment,
                }
            )
    return blocks


def _build_interpretation(
    file_items: list[dict[str, Any]],
    parsed_files: list[ParsedFileDiff],
    parsed_map: dict[str, ParsedFileDiff],
    *,
    filled_comments_map: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    output_files: list[dict[str, Any]] = []

    for index, item in enumerate(file_items):
        path = str(item.get("path") or "").strip()
        parsed = parsed_map.get(path) or (parsed_files[index] if index < len(parsed_files) else None)
        if not parsed:
            continue

        lines = parsed.after_code_lines
        comments = _normalize_comments(item.get("comments"), len(lines))
        if filled_comments_map:
            comments = filled_comments_map.get(parsed.display_path, comments)
        for line_index, line in enumerate(lines):
            if not line.code.strip():
                comments[line_index] = ""

        logic_before = str(item.get("logic_before") or "").strip()
        logic_after = str(item.get("logic_after") or "").strip()
        logic_diff = str(item.get("logic_diff") or "").strip()

        output_files.append(
            {
                "path": parsed.display_path,
                "language": code_block_lang(parsed.new_path or parsed.old_path),
                "blocks": _build_line_blocks(lines, comments),
                "summary": {
                    "before": logic_before or "暂无法判断",
                    "after": logic_after or "暂无法判断",
                    "diff": logic_diff or "暂无法判断",
                },
            }
        )

    return {"files": output_files}


def _build_summary_markdown(interpretation: dict[str, Any]) -> str:
    sections: list[str] = []
    for file_item in interpretation.get("files") or []:
        path = file_item.get("path") or "未知文件"
        summary = file_item.get("summary") or {}
        sections.append(f"## 文件：`{path}`")
        sections.append(
            "### 逻辑变化总结\n"
            f"- **修改前逻辑**：{summary.get('before', '暂无法判断')}\n"
            f"- **修改后逻辑**：{summary.get('after', '暂无法判断')}\n"
            f"- **核心差异**：{summary.get('diff', '暂无法判断')}"
        )
    return "\n\n".join(sections).strip()


async def run_code_interpretation(db: Session, *, diff_text: str, summary: str = "") -> dict[str, Any]:
    parsed_files = parse_unified_diff(diff_text)
    usable_files = [item for item in parsed_files if not item.is_binary and item.after_code_lines]

    if not usable_files:
        raise HTTPException(status_code=400, detail="未找到可解读的代码 diff 内容")

    llm_config = get_active_llm_config(db)
    user_parts: list[str] = []
    if summary.strip():
        user_parts.append(f"提交摘要：{summary.strip()}")
    user_parts.append("请为 lines 中每一行非空 code 都生成 comment（含 kind=context 的上下文行），不得遗漏；并返回 JSON：")
    user_parts.append(_build_comment_request(usable_files))
    user_content = "\n\n".join(user_parts)

    output_budget = suggest_output_tokens(llm_config.context_limit, cap=8192, ratio=0.35, floor=2000)
    try:
        result = await call_chat_completion(
            api_url=llm_config.api_url,
            api_key=llm_config.api_key,
            model_name=llm_config.model_name,
            messages=[
                {"role": "system", "content": CODE_COMMENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=output_budget,
            timeout=120.0,
            context_limit=llm_config.context_limit,
            response_format={"type": "json_object"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"代码解读调用失败：{exc}") from exc

    try:
        parsed_json = extract_test_cases_payload(result.get("content"), result.get("full_text"))
    except ValueError as exc:
        logger.warning("code_interpretation_parse_failed preview=%s", (result.get("full_text") or "")[:500])
        raise HTTPException(status_code=502, detail=f"代码解读返回格式无效：{exc}") from exc

    file_items = parsed_json.get("files")
    if not isinstance(file_items, list) or not file_items:
        raise HTTPException(status_code=502, detail="代码解读返回缺少 files 数组")

    parsed_map = {item.display_path: item for item in usable_files}
    for item in usable_files:
        parsed_map.setdefault(item.old_path, item)
        parsed_map.setdefault(item.new_path, item)

    filled_comments_map: dict[str, list[str]] = {}
    for index, item in enumerate(file_items):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        parsed = parsed_map.get(path) or (usable_files[index] if index < len(usable_files) else None)
        if not parsed:
            continue
        lines = parsed.after_code_lines
        comments = _normalize_comments(item.get("comments"), len(lines))
        for line_index, line in enumerate(lines):
            if not line.code.strip():
                comments[line_index] = ""
        comments = await _fill_missing_comments(
            llm_config=llm_config,
            lines=lines,
            comments=comments,
            path=parsed.display_path,
        )
        comments = _ensure_line_comments(lines, comments)
        filled_comments_map[parsed.display_path] = comments

    interpretation = _build_interpretation(
        file_items,
        usable_files,
        parsed_map,
        filled_comments_map=filled_comments_map,
    )
    if not interpretation.get("files"):
        raise HTTPException(status_code=502, detail="代码解读结果为空")

    return {
        "analysis": _build_summary_markdown(interpretation),
        "interpretation": interpretation,
        "model": result.get("model") or llm_config.model_name,
        "prompt_type": "代码解读",
        "prompt_name": "提交代码解读",
        "scenario": "code-interpretation",
        "truncated": False,
        "meta": {"files": len(interpretation.get("files") or [])},
    }

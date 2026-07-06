from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.llm_client import (
    call_chat_completion,
    stream_chat_completion,
    suggest_output_tokens,
    truncate_text_to_tokens,
)
from app.llm_config_service import get_active_llm_config
from app.prompt_template_service import get_prompt_template_for_type


def _estimate_diff_token_budget(context_limit: int) -> int:
    limit = max(4096, int(context_limit or 128000))
    return min(60000, max(8000, int(limit * 0.45)))


_ANALYSIS_SECTION_MARKERS = (
    "## 🎯 30秒结论",
    "## 🎯",
    "## 30秒结论",
    "## 📊 影响范围速览",
    "## 🔍 主要改动点",
)
_SECTION_START_RE = re.compile(
    r"##\s*[🎯📊🔍]?\s*(?:30\s*秒\s*结论|影响范围速览|主要改动点)"
)


def strip_analysis_preamble(text: str) -> str:
    """去掉模型在正式章节标题前输出的思考/铺垫文字。"""
    normalized = (text or "").strip()
    if not normalized:
        return normalized

    best_idx = -1
    for marker in _ANALYSIS_SECTION_MARKERS:
        idx = normalized.find(marker)
        if idx >= 0 and (best_idx < 0 or idx < best_idx):
            best_idx = idx
    if best_idx > 0:
        return normalized[best_idx:].strip()
    if best_idx == 0:
        return normalized

    match = _SECTION_START_RE.search(normalized)
    if match and match.start() > 0:
        return normalized[match.start() :].strip()
    if match and match.start() == 0:
        return normalized

    match = re.search(r"(?m)^##\s+", normalized)
    if match:
        return normalized[match.start() :].strip()
    return normalized


def _build_user_prompt(
    *,
    scenario: str,
    title: str,
    summary: str,
    context: str,
    content: str,
    content_label: str,
    diff_truncated: bool,
    extra: dict[str, Any] | None = None,
) -> str:
    parts: list[str] = []
    if scenario:
        parts.append(f"分析场景：{scenario}")
    if title:
        parts.append(f"标题：{title}")
    if summary:
        parts.append(f"摘要：{summary}")
    if extra:
        for key, value in extra.items():
            if value in (None, ""):
                continue
            parts.append(f"{key}：{value}")
    if context:
        parts.append(f"补充上下文：\n{context.strip()}")
    if content:
        parts.append(f"{content_label}：\n{content.strip()}")
    if diff_truncated:
        parts.append("注意：变更内容因上下文限制已被截断，请在分析末尾说明可能遗漏的部分。")
    if not parts:
        raise ValueError("缺少待分析内容")
    return "\n\n".join(parts)


async def _prepare_ai_analysis(db: Session, payload: dict) -> dict[str, Any]:
    scenario = str(payload.get("scenario") or "generic").strip()
    prompt_type = str(payload.get("prompt_type") or "").strip()
    if not prompt_type:
        prompt_type = "代码解读" if scenario == "code-interpretation" else "AI分析"

    title = str(payload.get("title") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    context = str(payload.get("context") or "").strip()
    content = str(payload.get("content") or "").strip()
    content_label = str(payload.get("content_label") or "变更内容").strip() or "变更内容"
    extra: dict[str, Any] = dict(payload.get("extra") or {})

    log_id = payload.get("log_id")
    if log_id is not None:
        from app.services import get_activity_log, get_or_fetch_log_diff

        log = get_activity_log(db, int(log_id))
        if not log:
            raise ValueError("日志不存在")
        if not title:
            title = str(log.title or "").strip()
        if not summary:
            summary = str(log.summary or "").strip()
        if not scenario or scenario == "generic":
            scenario = "commit-diff"
        diff_data = await get_or_fetch_log_diff(db, log)
        if not content:
            content = str(diff_data.get("diff") or "").strip()
        extra.setdefault("仓库", diff_data.get("repo") or "")
        extra.setdefault("分支", diff_data.get("branch") or "")
        extra.setdefault("提交", diff_data.get("commit_sha") or "")

        if scenario == "code-interpretation":
            return {
                "mode": "code-interpretation",
                "scenario": scenario,
                "prompt_type": prompt_type,
                "summary": summary,
                "content": content,
            }

    if scenario == "code-interpretation":
        if not content:
            raise ValueError("缺少代码 diff 内容")
        return {
            "mode": "code-interpretation",
            "scenario": scenario,
            "prompt_type": prompt_type,
            "summary": summary,
            "content": content,
        }

    prompt = get_prompt_template_for_type(db, prompt_type)
    llm_config = get_active_llm_config(db)

    diff_truncated = False
    if content:
        diff_budget = _estimate_diff_token_budget(llm_config.context_limit)
        original_len = len(content)
        trimmed = truncate_text_to_tokens(content, diff_budget)
        diff_truncated = len(trimmed) < original_len
        content = trimmed

    user_content = _build_user_prompt(
        scenario=scenario,
        title=title,
        summary=summary,
        context=context,
        content=content,
        content_label=content_label,
        diff_truncated=diff_truncated,
        extra=extra,
    )

    output_budget = suggest_output_tokens(llm_config.context_limit, cap=4096, ratio=0.2, floor=800)
    return {
        "mode": "analysis",
        "scenario": scenario,
        "prompt_type": prompt_type,
        "prompt_name": prompt.name,
        "prompt_content": prompt.content,
        "llm_config": llm_config,
        "user_content": user_content,
        "diff_truncated": diff_truncated,
        "extra": extra,
        "output_budget": output_budget,
    }


def _build_analysis_result(
    *,
    analysis: str,
    prepared: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    extra = prepared.get("extra") or {}
    return {
        "analysis": strip_analysis_preamble(analysis),
        "model": model,
        "prompt_type": prepared["prompt_type"],
        "prompt_name": prepared.get("prompt_name") or "",
        "scenario": prepared.get("scenario") or "",
        "truncated": bool(prepared.get("diff_truncated")),
        "meta": {key: value for key, value in extra.items() if value not in (None, "")},
    }


async def run_ai_analysis(db: Session, payload: dict) -> dict:
    prepared = await _prepare_ai_analysis(db, payload)

    if prepared.get("mode") == "code-interpretation":
        from app.code_interpretation_service import run_code_interpretation

        return await run_code_interpretation(
            db,
            diff_text=str(prepared.get("content") or ""),
            summary=str(prepared.get("summary") or ""),
        )

    llm_config = prepared["llm_config"]
    messages = [
        {"role": "system", "content": prepared["prompt_content"]},
        {"role": "user", "content": prepared["user_content"]},
    ]
    try:
        result = await call_chat_completion(
            api_url=llm_config.api_url,
            api_key=llm_config.api_key,
            model_name=llm_config.model_name,
            messages=messages,
            temperature=0.2,
            max_tokens=int(prepared["output_budget"]),
            timeout=120.0,
            context_limit=llm_config.context_limit,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 分析调用失败：{exc}") from exc

    analysis = (result.get("full_text") or result.get("content") or "").strip()
    if not analysis:
        raise HTTPException(status_code=502, detail="LLM 未返回有效分析内容")

    return _build_analysis_result(
        analysis=analysis,
        prepared=prepared,
        model=str(result.get("model") or llm_config.model_name),
    )


async def stream_ai_analysis_events(db: Session, payload: dict) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "status", "message": "正在准备分析上下文…"}

    try:
        prepared = await _prepare_ai_analysis(db, payload)
    except ValueError as exc:
        yield {"type": "error", "detail": str(exc)}
        return
    except HTTPException as exc:
        yield {"type": "error", "detail": str(exc.detail)}
        return

    if prepared.get("mode") == "code-interpretation":
        yield {"type": "status", "message": "正在解读代码，请稍候…"}
        try:
            from app.code_interpretation_service import run_code_interpretation

            result = await run_code_interpretation(
                db,
                diff_text=str(prepared.get("content") or ""),
                summary=str(prepared.get("summary") or ""),
            )
        except HTTPException as exc:
            yield {"type": "error", "detail": str(exc.detail)}
            return
        except Exception as exc:
            yield {"type": "error", "detail": f"代码解读失败：{exc}"}
            return
        yield {"type": "done", "result": result}
        return

    llm_config = prepared["llm_config"]
    messages = [
        {"role": "system", "content": prepared["prompt_content"]},
        {"role": "user", "content": prepared["user_content"]},
    ]

    if not llm_config.stream_enabled:
        yield {"type": "status", "message": "当前模型未启用流式，正在生成完整结果…"}
        try:
            result = await run_ai_analysis(db, payload)
        except HTTPException as exc:
            yield {"type": "error", "detail": str(exc.detail)}
            return
        yield {"type": "done", "result": result}
        return

    yield {"type": "status", "message": "正在连接模型并流式生成…"}

    reasoning_parts: list[str] = []
    content_parts: list[str] = []
    resolved_model = llm_config.model_name

    try:
        async for chunk in stream_chat_completion(
            api_url=llm_config.api_url,
            api_key=llm_config.api_key,
            model_name=llm_config.model_name,
            messages=messages,
            temperature=0.2,
            max_tokens=int(prepared["output_budget"]),
            timeout=120.0,
            context_limit=llm_config.context_limit,
        ):
            kind = chunk.get("kind")
            if kind == "reasoning":
                delta = str(chunk.get("delta") or "")
                if not delta:
                    continue
                reasoning_parts.append(delta)
                yield {
                    "type": "reasoning",
                    "delta": delta,
                    "text": "".join(reasoning_parts),
                }
            elif kind == "content":
                delta = str(chunk.get("delta") or "")
                if not delta:
                    continue
                content_parts.append(delta)
                yield {
                    "type": "content",
                    "delta": delta,
                    "text": "".join(content_parts),
                }
            elif kind == "done":
                resolved_model = str(chunk.get("model") or resolved_model)
    except HTTPException as exc:
        yield {"type": "error", "detail": str(exc.detail)}
        return
    except Exception as exc:
        yield {"type": "error", "detail": f"AI 分析调用失败：{exc}"}
        return

    analysis = "".join(content_parts).strip()
    if not analysis:
        analysis = "".join(reasoning_parts).strip()
    if not analysis:
        yield {"type": "error", "detail": "LLM 未返回有效分析内容"}
        return

    yield {
        "type": "done",
        "result": _build_analysis_result(
            analysis=analysis,
            prepared=prepared,
            model=resolved_model,
        ),
    }


def serialize_analysis_context(**kwargs: Any) -> str:
    return json.dumps(kwargs, ensure_ascii=False, indent=2)

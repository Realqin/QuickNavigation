from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.llm_client import call_chat_completion, suggest_output_tokens, truncate_text_to_tokens
from app.llm_config_service import get_active_llm_config
from app.prompt_template_service import get_prompt_template_for_type


def _estimate_diff_token_budget(context_limit: int) -> int:
    limit = max(4096, int(context_limit or 128000))
    return min(60000, max(8000, int(limit * 0.45)))


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


async def run_ai_analysis(db: Session, payload: dict) -> dict:
    prompt_type = str(payload.get("prompt_type") or "AI分析").strip() or "AI分析"
    prompt = get_prompt_template_for_type(db, prompt_type)
    llm_config = get_active_llm_config(db)

    scenario = str(payload.get("scenario") or "generic").strip()
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
    try:
        result = await call_chat_completion(
            api_url=llm_config.api_url,
            api_key=llm_config.api_key,
            model_name=llm_config.model_name,
            messages=[
                {"role": "system", "content": prompt.content},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=output_budget,
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

    return {
        "analysis": analysis,
        "model": result.get("model") or llm_config.model_name,
        "prompt_type": prompt_type,
        "prompt_name": prompt.name,
        "scenario": scenario,
        "truncated": diff_truncated,
        "meta": {key: value for key, value in extra.items() if value not in (None, "")},
    }


def serialize_analysis_context(**kwargs: Any) -> str:
    return json.dumps(kwargs, ensure_ascii=False, indent=2)

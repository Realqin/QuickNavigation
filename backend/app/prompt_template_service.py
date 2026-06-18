from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import PromptTemplate


PROMPT_TYPE_OPTIONS = ("通用对话", "需求评审", "测试用例", "缺陷分析", "接口用例", "AI分析")

GENERAL_AI_ANALYSIS_BASE_CONTENT = (
    "你是资深软件工程与测试分析专家。用户会提供代码变更、配置变更、接口变更或业务变更的描述与 diff。"
    "请基于输入做结构化解读，帮助研发与测试快速理解「改了什么、影响多大、要测什么」。"
    "输出使用 Markdown 正文，按章节组织，语言简洁、可执行，避免空泛套话。"
    "必须包含以下章节（无相关信息时写「无明显变化」或「暂无法从 diff 判断」）："
    "1. 变更概览；2. 影响评估（高/中/低 + 理由）；3. 主要逻辑改动点；"
    "4. 风险与回归建议；5. 测试关注点。"
    "要求：结合文件路径、类名、方法名说明改动；区分业务逻辑、接口契约、配置、依赖、数据库等类型；"
    "若输入 diff 被截断，在文末单独说明可能遗漏。"
)

GENERAL_AI_ANALYSIS_RESPONSE_FORMAT = (
    "使用 Markdown 正文输出，包含二级标题（##），不要使用 JSON 或代码块包裹整段回复。"
)

API_CASE_GENERATE_BASE_CONTENT = (
    "你是接口测试专家。根据提供的 HTTP 接口信息，生成一组可执行的冒烟与关键异常场景测试用例。"
    "至少覆盖：正常流程、必填字段校验（适用于 POST/PUT/PATCH）、鉴权校验（若接口需要认证）。"
    "用例 id 从 TC001 递增；apiUrl 使用接口实际路径；headers 中 Authorization 使用 Bearer ${token} 占位符。"
    "【用例名称 name】必须具体、可区分，12~36 字为宜，让读者不看 description 也能知道测什么。"
    "命名建议采用「场景-关键条件-预期结果」结构，例如："
    "「正常分页查询用户列表-返回200」「创建用户缺少username-返回400」「未携带Token访问-返回401」。"
    "name 中应包含：被测动作或对象、关键参数/缺失项/异常条件、预期状态码或结果关键词（至少两项）。"
    "禁止使用过于笼统的名称，如「正常流程」「冒烟测试」「接口测试」「成功场景」「失败场景」。"
    "description 用于补充请求细节与断言说明，可与 name 相关但不要与 name 完全相同。"
    "【重要】只输出一个 JSON 对象，必须包含 testCases 数组；不要 Markdown 代码块，不要任何解释文字。"
)

API_CASE_GENERATE_RESPONSE_FORMAT = """{
  "testCases": [
    {
      "id": "TC001",
      "name": "正常分页查询用户列表-返回200",
      "apiUrl": "/api/v1/users",
      "method": "GET",
      "headers": {"Content-Type": "application/json", "Authorization": "Bearer ${token}"},
      "requestData": {"page": 1, "size": 10},
      "expectedStatusCode": 200,
      "expectedResponse": {"code": 0, "data": {"users": []}},
      "caseType": "正常流程",
      "description": "有效认证获取用户列表"
    },
    {
      "id": "TC002",
      "name": "创建用户缺少username-返回400",
      "apiUrl": "/api/v1/users",
      "method": "POST",
      "headers": {"Content-Type": "application/json", "Authorization": "Bearer ${token}"},
      "requestData": {"email": "test@x.com", "password": "123456"},
      "expectedStatusCode": 400,
      "expectedResponse": {"code": 400, "message": "username为必填项"},
      "caseType": "必填字段校验",
      "description": "创建用户缺少username"
    },
    {
      "id": "TC003",
      "name": "未携带Token访问用户列表-返回401",
      "apiUrl": "/api/v1/users",
      "method": "GET",
      "headers": {"Content-Type": "application/json"},
      "requestData": null,
      "expectedStatusCode": 401,
      "expectedResponse": {"code": 401, "message": "未授权"},
      "caseType": "鉴权校验",
      "description": "无token返回401"
    }
  ]
}"""


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _normalize_prompt_text(value: str) -> str:
    text = str(value or "")
    if "\\" not in text:
        return text
    return (
        text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\'", "'")
    )


def _compose_prompt_content(base_content: str, response_type: str, response_format: str) -> str:
    sections = [str(base_content or "").strip()]
    if response_type:
        sections.append(f"返回类型：{response_type}")
    if response_format:
        sections.append(f"返回格式：\n{response_format}")
    return "\n\n".join(section for section in sections if section).strip()


def _resolve_prompt_fields(payload: dict) -> tuple[str, str, str, str]:
    raw_content = _normalize_prompt_text(payload.get("content", ""))
    extra = payload.get("extra_data") or {}
    base_content = _normalize_prompt_text(payload.get("base_content", "") or extra.get("base_content", "")) or raw_content
    response_type = str(payload.get("response_type", "") or extra.get("response_type", "") or "").strip()
    response_format = _normalize_prompt_text(payload.get("response_format", "") or extra.get("response_format", ""))
    rendered_content = _compose_prompt_content(base_content, response_type, response_format)
    return base_content, response_type, response_format, rendered_content


def _serialize(prompt: PromptTemplate) -> dict:
    extra = prompt.extra_data or {}
    base_content, response_type, response_format, rendered_content = _resolve_prompt_fields(
        {
            "content": prompt.content,
            "base_content": extra.get("base_content", ""),
            "response_type": extra.get("response_type", ""),
            "response_format": extra.get("response_format", ""),
            "extra_data": extra,
        }
    )
    return {
        "id": prompt.id,
        "prompt_type": prompt.prompt_type,
        "name": prompt.name,
        "description": prompt.description,
        "content": rendered_content,
        "base_content": base_content,
        "response_type": response_type,
        "response_format": response_format,
        "remark": prompt.remark,
        "enabled": prompt.enabled,
        "is_default": prompt.is_default,
        "is_preset": prompt.is_preset,
        "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
    }


def _unset_defaults(db: Session, prompt_type: str, current_id: str) -> None:
    rows = (
        db.query(PromptTemplate)
        .filter(
            PromptTemplate.id != current_id,
            PromptTemplate.prompt_type == prompt_type,
            PromptTemplate.is_default.is_(True),
        )
        .all()
    )
    now = datetime.utcnow()
    for row in rows:
        row.is_default = False
        row.updated_at = now


def list_prompt_templates(db: Session) -> list[dict]:
    rows = db.query(PromptTemplate).order_by(PromptTemplate.created_at.asc()).all()
    return [_serialize(row) for row in rows]


def create_prompt_template(db: Session, payload: dict) -> dict:
    now = datetime.utcnow()
    base_content, response_type, response_format, rendered_content = _resolve_prompt_fields(payload)
    prompt = PromptTemplate(
        id=_new_id(),
        prompt_type=payload["prompt_type"],
        name=payload["name"],
        description=payload.get("description", ""),
        content=rendered_content,
        remark=payload.get("remark", ""),
        enabled=payload.get("enabled", True),
        is_default=payload.get("is_default", False),
        is_preset=payload.get("is_preset", False),
        extra_data={
            "base_content": base_content,
            "response_type": response_type,
            "response_format": response_format,
        },
        created_at=now,
        updated_at=now,
    )
    db.add(prompt)
    if prompt.is_default:
        _unset_defaults(db, prompt.prompt_type, prompt.id)
    db.commit()


def ensure_general_ai_analysis_prompt(db: Session) -> None:
    """确保预制「通用变更分析」提示词存在且内容为最新。"""
    now = datetime.utcnow()
    prompt = (
        db.query(PromptTemplate)
        .filter(PromptTemplate.remark == "general-ai-analysis", PromptTemplate.is_preset.is_(True))
        .first()
    )
    content = _compose_prompt_content(
        GENERAL_AI_ANALYSIS_BASE_CONTENT,
        "markdown",
        GENERAL_AI_ANALYSIS_RESPONSE_FORMAT,
    )
    extra = {
        "base_content": GENERAL_AI_ANALYSIS_BASE_CONTENT,
        "response_type": "markdown",
        "response_format": GENERAL_AI_ANALYSIS_RESPONSE_FORMAT,
    }
    if prompt:
        prompt.content = content
        prompt.extra_data = extra
        prompt.description = "适用于提交 diff、配置变更、接口变更等场景的影响与逻辑分析。"
        prompt.updated_at = now
        db.commit()
        return

    db.add(
        PromptTemplate(
            id=_new_id(),
            prompt_type="AI分析",
            name="通用变更分析",
            description="适用于提交 diff、配置变更、接口变更等场景的影响与逻辑分析。",
            content=content,
            remark="general-ai-analysis",
            enabled=True,
            is_default=True,
            is_preset=True,
            extra_data=extra,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    db.refresh(prompt)
    return _serialize(prompt)


def update_prompt_template(db: Session, prompt_id: str, payload: dict) -> dict:
    prompt = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="提示词不存在")

    is_preset = prompt.is_preset
    base_content, response_type, response_format, rendered_content = _resolve_prompt_fields(payload)
    prompt.prompt_type = payload["prompt_type"]
    prompt.name = payload["name"]
    prompt.description = payload.get("description", "")
    prompt.content = rendered_content
    prompt.remark = payload.get("remark", prompt.remark)
    prompt.enabled = payload.get("enabled", True)
    prompt.is_default = payload.get("is_default", False)
    prompt.is_preset = is_preset
    prompt.extra_data = {
        "base_content": base_content,
        "response_type": response_type,
        "response_format": response_format,
    }
    prompt.updated_at = datetime.utcnow()
    if prompt.is_default:
        _unset_defaults(db, prompt.prompt_type, prompt.id)
    db.commit()
    db.refresh(prompt)
    return _serialize(prompt)


def toggle_prompt_template(db: Session, prompt_id: str, enabled: bool) -> dict:
    prompt = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="提示词不存在")
    prompt.enabled = enabled
    prompt.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prompt)
    return _serialize(prompt)


def delete_prompt_template(db: Session, prompt_id: str) -> None:
    prompt = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="提示词不存在")
    db.delete(prompt)
    db.commit()


def get_prompt_template_for_type(db: Session, prompt_type: str) -> PromptTemplate:
    rows = (
        db.query(PromptTemplate)
        .filter(PromptTemplate.enabled.is_(True), PromptTemplate.prompt_type == prompt_type)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=400, detail=f"未找到启用的提示词：{prompt_type}")
    default_item = next((row for row in rows if row.is_default), None)
    if default_item:
        return default_item
    rows.sort(key=lambda item: item.updated_at or datetime.min, reverse=True)
    return rows[0]


def seed_prompt_templates(db: Session) -> None:
    if db.query(PromptTemplate).count() > 0:
        return
    now = datetime.utcnow()
    seeds = [
        {
            "prompt_type": "通用对话",
            "name": "默认通用提示词",
            "description": "默认的测试助手提示词，适用于日常问答与分析。",
            "base_content": "你是一位专业的测试工程助手，擅长需求分析、用例设计、缺陷分析和测试建议。请用清晰、简洁、可执行的方式回答问题。",
            "response_type": "",
            "response_format": "",
            "remark": "",
            "enabled": True,
            "is_default": True,
            "is_preset": True,
        },
        {
            "prompt_type": "需求评审",
            "name": "可测性分析",
            "description": "用于输出需求文档的可测性分析结果。",
            "base_content": "请基于需求文档输出可测性分析结果，重点说明哪些信息缺失会导致无法编写测试用例或无法判断通过失败。",
            "response_type": "",
            "response_format": "",
            "remark": "",
            "enabled": True,
            "is_default": False,
            "is_preset": True,
        },
        {
            "prompt_type": "接口用例",
            "name": "接口冒烟用例生成",
            "description": "根据接口文档生成基础冒烟测试用例，用例名称需包含场景、条件与预期。",
            "base_content": API_CASE_GENERATE_BASE_CONTENT,
            "response_type": "json-object",
            "response_format": API_CASE_GENERATE_RESPONSE_FORMAT,
            "remark": "api-case-generate",
            "enabled": True,
            "is_default": True,
            "is_preset": True,
        },
        {
            "prompt_type": "AI分析",
            "name": "通用变更分析",
            "description": "适用于提交 diff、配置变更、接口变更等场景的影响与逻辑分析。",
            "base_content": GENERAL_AI_ANALYSIS_BASE_CONTENT,
            "response_type": "markdown",
            "response_format": GENERAL_AI_ANALYSIS_RESPONSE_FORMAT,
            "remark": "general-ai-analysis",
            "enabled": True,
            "is_default": True,
            "is_preset": True,
        },
    ]
    for item in seeds:
        base_content = item["base_content"]
        response_type = item["response_type"]
        response_format = item["response_format"]
        content = _compose_prompt_content(base_content, response_type, response_format)
        db.add(
            PromptTemplate(
                id=_new_id(),
                prompt_type=item["prompt_type"],
                name=item["name"],
                description=item["description"],
                content=content,
                remark=item["remark"],
                enabled=item["enabled"],
                is_default=item["is_default"],
                is_preset=item["is_preset"],
                extra_data={
                    "base_content": base_content,
                    "response_type": response_type,
                    "response_format": response_format,
                },
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()


def sync_api_case_generate_prompt(db: Session) -> None:
    """同步预制「接口冒烟用例生成」提示词的返回格式（已有库也能更新）。"""
    prompt = (
        db.query(PromptTemplate)
        .filter(PromptTemplate.remark == "api-case-generate", PromptTemplate.is_preset.is_(True))
        .first()
    )
    if not prompt:
        return

    extra = dict(prompt.extra_data or {})
    extra["base_content"] = API_CASE_GENERATE_BASE_CONTENT
    extra["response_type"] = "json-object"
    extra["response_format"] = API_CASE_GENERATE_RESPONSE_FORMAT
    prompt.content = _compose_prompt_content(
        API_CASE_GENERATE_BASE_CONTENT,
        "json-object",
        API_CASE_GENERATE_RESPONSE_FORMAT,
    )
    prompt.extra_data = extra
    prompt.updated_at = datetime.utcnow()
    db.commit()

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import PromptTemplate


PROMPT_TYPE_OPTIONS = ("通用对话", "需求评审", "测试用例", "缺陷分析", "接口用例", "AI分析", "代码解读")

GENERAL_AI_ANALYSIS_BASE_CONTENT = (
    "# Role\n"
    "你是精通软件架构与质量保障的技术专家，负责对代码、配置、接口或业务变更（含 diff）做结构化解读，"
    "帮助研发与测试快速理解影响范围与测试重点。\n\n"
    "# 核心原则\n"
    "- **结论前置**：开头必须让人 30 秒内判断「影响大不大」\n"
    "- **风险必带图标**：全文凡涉及风险/优先级，必须使用 🔴 高风险、🟡 中风险、🟢 低风险，禁止只用文字\n"
    "- **可执行**：每条建议对应具体测试动作，不说空话\n"
    "- **简洁**：只写关键信息，避免套话\n\n"
    "# 输出禁令\n"
    "- 回复第一个字符必须是 `#`，直接从 `## 🎯 30秒结论` 开始\n"
    "- 禁止在正式章节前输出思考过程、口头分析、要点梳理或任何铺垫文字\n"
    "- 禁止输出「先快速理解」「需要基于 diff」「输出格式严格按照要求」等过渡句\n\n"
    "# 输入说明\n"
    "用户可能提供 diff、配置变更、接口变更或业务描述；可能只有一种或多种。\n"
    "未涉及的维度在对应位置写「无明显变化」。\n"
    "若 diff 或描述明显不完整（如被截断），必须在「📌 补充说明」中列出可能遗漏的内容。"
)

GENERAL_AI_ANALYSIS_RESPONSE_FORMAT = (
    "必须严格按以下 Markdown 结构输出，不得增删章节标题；"
    "使用 Markdown 正文，不要用 JSON 或代码块包裹整段回复；"
    "回复必须直接从 `## 🎯 30秒结论` 开始，之前不得有任何文字。\n\n"
    "## 🎯 30秒结论\n\n"
    "| 维度 | 结论 |\n"
    "|------|------|\n"
    "| 影响等级 | 🔴 高风险 / 🟡 中风险 / 🟢 低风险（三选一，必须带图标） |\n"
    "| 影响范围 | 列出有影响的项：🗄️表结构 \\| 🔌接口 \\| ⚙️配置 \\| 📦依赖 \\| 🧩业务逻辑 \\| 🎨前端界面 |\n"
    "| 变更类型 | 新增功能 / Bug修复 / 重构 / 配置调整 / 性能优化 |\n\n"
    "> **一句话总结**：（本次改了什么、主要影响哪个模块、重点测什么）\n\n"
    "## 📊 影响范围速览\n\n"
    "| 类型 | 是否有变更 | 详细说明 |\n"
    "|------|-----------|----------|\n"
    "| 🗄️ 数据库表结构 | ✅ / ❌ | 有变更时简述，无则写「无」 |\n"
    "| 🔌 API 接口 | ✅ / ❌ | |\n"
    "| ⚙️ 配置项 | ✅ / ❌ | |\n"
    "| 📦 依赖包 | ✅ / ❌ | |\n"
    "| 🧩 业务逻辑 | ✅ / ❌ | |\n"
    "| 🎨 前端界面 | ✅ / ❌ | |\n\n"
    "## 🔍 主要改动点\n\n"
    "| 序号 | 改动类型 | 文件/类/方法 | 改动说明 | 风险 |\n"
    "|------|----------|--------------|----------|------|\n"
    "| 1 | 业务逻辑/接口/配置/依赖等 | `路径或符号` | 改了什么 | 🔴/🟡/🟢 |\n\n"
    "（无法从 diff 判断时写一行「暂无法从 diff 判断」）\n\n"
    "## ⚠️ 风险与回归建议\n\n"
    "### 🔴 高风险（必须回归）\n"
    "- [ ] 具体场景与验证点\n\n"
    "### 🟡 中风险（建议回归）\n"
    "- [ ] 具体场景与验证点\n\n"
    "### 🟢 低风险（了解即可）\n"
    "- [ ] 具体场景\n\n"
    "（某档无项时写「无」）\n\n"
    "## 🧪 测试关注点\n\n"
    "| 类别 | 关注点 | 验证方式 | 优先级 |\n"
    "|------|--------|----------|--------|\n"
    "| 功能测试 | | 手工/自动化 | 🔴/🟡/🟢 |\n"
    "| 接口测试 | | 接口测试 | 🔴/🟡/🟢 |\n"
    "| 回归测试 | | 回归用例 | 🔴/🟡/🟢 |\n\n"
    "## 📌 补充说明\n\n"
    "（diff 截断或信息不足时说明遗漏；否则写「无」）"
)

CODE_INTERPRETATION_BASE_CONTENT = (
    "你是代码讲解专家。用户会提供 unified diff。"
    "你的输出必须分两步完成，顺序不可颠倒："
    "【第一步：原样展示代码】"
    "从 diff 中提取变更涉及的代码片段，放入 Markdown 代码块中。"
    "代码必须与 diff 原文一字不差：不得改写、缩写、省略、换行合并或调整空格/缩进/标点。"
    "只展示 diff 中实际变更的 hunk；纯新增只展示修改后，纯删除只展示修改前，修改则分别展示修改前与修改后。"
    "【第二步：逐行加注释】"
    "在第一步展示的代码块内，给每一行（含空行、仅含 { } 的行）在**行尾**追加中文注释，说明该行含义。"
    "注释格式：两个空格 + 单行注释符 + 「备注：」+ 中文解释。"
    "单行注释符按语言选择：Java/C/JS/TS/Go 等用 //；Python/YAML 用 #；SQL 用 --；"
    "若无法确定语言，默认用 //。"
    "示例（注意代码原文未被改动，只在行尾追加备注）："
    "```java\n"
    "if (user == null) {  // 备注：判断 user 是否为空\n"
    "    throw new BizException(\"用户不存在\");  // 备注：用户不存在时抛出业务异常\n"
    "}\n"
    "```\n"
    "【第三步：逻辑变化总结】"
    "每个文件在代码块之后，用简短条目说明：修改前逻辑、修改后逻辑、核心差异。"
    "【硬性禁止】"
    "禁止用表格代替代码；禁止只写文字描述而不展示完整代码；"
    "禁止输出测试建议、风险评级、回归清单；禁止修改任何原始代码字符。"
)

CODE_INTERPRETATION_RESPONSE_FORMAT = (
    "使用 Markdown 输出，每个变更文件一组，结构如下：\n\n"
    "## 文件：`路径/文件名`\n\n"
    "### 修改前代码\n"
    "（若无删除/修改前内容，写「无」）\n"
    "```java\n"
    "    return null;  // 备注：查不到用户时直接返回 null\n"
    "```\n\n"
    "### 修改后代码\n"
    "（若无新增/修改后内容，写「无」）\n"
    "```java\n"
    "    throw new BizException(\"用户不存在\");  // 备注：查不到用户时抛出业务异常\n"
    "```\n\n"
    "### 逻辑变化总结\n"
    "- **修改前逻辑**：...\n"
    "- **修改后逻辑**：...\n"
    "- **核心差异**：...\n\n"
    "再次强调：代码块内的源码文本必须与 diff 完全一致，备注只能追加在行尾，不能插入到代码中间。"
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


def ensure_code_interpretation_prompt(db: Session) -> None:
    """确保预制「提交代码解读」提示词存在且内容为最新。"""
    now = datetime.utcnow()
    prompt = (
        db.query(PromptTemplate)
        .filter(PromptTemplate.remark == "code-interpretation", PromptTemplate.is_preset.is_(True))
        .first()
    )
    content = _compose_prompt_content(
        CODE_INTERPRETATION_BASE_CONTENT,
        "markdown",
        CODE_INTERPRETATION_RESPONSE_FORMAT,
    )
    extra = {
        "base_content": CODE_INTERPRETATION_BASE_CONTENT,
        "response_type": "markdown",
        "response_format": CODE_INTERPRETATION_RESPONSE_FORMAT,
    }
    if prompt:
        prompt.content = content
        prompt.extra_data = extra
        prompt.description = "展示变更代码并逐行备注解读，总结修改前后逻辑差异。"
        prompt.updated_at = now
        db.commit()
        return

    db.add(
        PromptTemplate(
            id=_new_id(),
            prompt_type="代码解读",
            name="提交代码解读",
            description="展示变更代码并逐行备注解读，总结修改前后逻辑差异。",
            content=content,
            remark="code-interpretation",
            enabled=True,
            is_default=True,
            is_preset=True,
            extra_data=extra,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


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

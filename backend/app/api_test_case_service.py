from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.llm_client import call_chat_completion, extract_test_cases_payload, suggest_output_tokens
from app.llm_config_service import get_active_llm_config
from app.models import ApiTestCase, DictItem
from app.prompt_template_service import get_prompt_template_for_type
from app.services import DICT_ENVIRONMENT, DICT_PROJECT

logger = logging.getLogger(__name__)
VALID_CASE_TYPES = {"smoke", "boundary", "regression", "custom"}
VALID_STATUSES = {"active", "deleted"}

LLM_CASE_TYPE_MAP = {
    "正常流程": "smoke",
    "冒烟": "smoke",
    "冒烟测试": "smoke",
    "必填字段校验": "boundary",
    "边界": "boundary",
    "边界值": "boundary",
    "参数校验": "boundary",
    "鉴权校验": "custom",
    "鉴权": "custom",
    "回归": "regression",
}

def _dict_name_map(db: Session, dict_type: str) -> dict[int, str]:
    rows = db.query(DictItem).filter(DictItem.dict_type == dict_type).all()
    return {row.id: row.name for row in rows}


def _normalize_method(method: str) -> str:
    return (method or "GET").strip().upper()


def _case_to_dict(case: ApiTestCase, *, project_map: dict[int, str], env_map: dict[int, str]) -> dict:
    return {
        "id": case.id,
        "project_id": case.project_id,
        "environment_id": case.environment_id,
        "project_display": project_map.get(case.project_id, str(case.project_id)),
        "environment_display": env_map.get(case.environment_id, str(case.environment_id)),
        "service": case.service,
        "name": case.name,
        "api_path": case.api_path,
        "method": case.method,
        "request_headers": case.request_headers,
        "request_params": case.request_params,
        "request_body": case.request_body,
        "expected_status": case.expected_status,
        "expected_response": case.expected_response,
        "response_assert_mode": case.response_assert_mode or "text",
        "response_assert_rules": case.response_assert_rules,
        "case_type": case.case_type,
        "status": case.status,
        "endpoint_id": case.endpoint_id,
        "last_exec_pass": case.last_exec_pass,
        "last_exec_status_code": case.last_exec_status_code,
        "last_exec_response": case.last_exec_response,
        "last_exec_detail": case.last_exec_detail,
        "last_exec_at": case.last_exec_at,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "deleted_at": case.deleted_at,
    }


def list_api_test_cases(
    db: Session,
    *,
    project_id: int | None = None,
    environment_id: int | None = None,
    service: str | None = None,
    endpoint_id: str | None = None,
    keyword: str | None = None,
    status: str = "active",
    page: int = 1,
    page_size: int = 10,
) -> dict:
    query = db.query(ApiTestCase)
    status_norm = (status or "active").strip().lower()
    if status_norm == "active":
        query = query.filter(
            ApiTestCase.status == "active",
            ApiTestCase.deleted_at.is_(None),
        )
    elif status_norm == "deleted":
        query = query.filter(ApiTestCase.status == "deleted")
    elif status_norm != "all":
        raise ValueError("status 仅支持 active / deleted / all")

    if project_id is not None:
        query = query.filter(ApiTestCase.project_id == project_id)
    if environment_id is not None:
        query = query.filter(ApiTestCase.environment_id == environment_id)
    if service:
        query = query.filter(ApiTestCase.service.ilike(f"%{service.strip()}%"))
    if endpoint_id:
        query = query.filter(ApiTestCase.endpoint_id == endpoint_id.strip())
    if keyword:
        kw = f"%{keyword.strip()}%"
        query = query.filter(
            (ApiTestCase.name.ilike(kw))
            | (ApiTestCase.api_path.ilike(kw))
            | (ApiTestCase.service.ilike(kw))
        )

    total = query.count()
    rows = (
        query.order_by(ApiTestCase.updated_at.desc(), ApiTestCase.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    project_map = _dict_name_map(db, DICT_PROJECT)
    env_map = _dict_name_map(db, DICT_ENVIRONMENT)
    return {
        "items": [_case_to_dict(row, project_map=project_map, env_map=env_map) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_api_test_case(db: Session, case_id: int) -> dict:
    case = db.query(ApiTestCase).filter(ApiTestCase.id == case_id).first()
    if not case:
        raise ValueError("用例不存在")
    project_map = _dict_name_map(db, DICT_PROJECT)
    env_map = _dict_name_map(db, DICT_ENVIRONMENT)
    return _case_to_dict(case, project_map=project_map, env_map=env_map)


def create_api_test_case(db: Session, payload: dict) -> dict:
    case_type = str(payload.get("case_type") or "smoke").strip().lower()
    if case_type not in VALID_CASE_TYPES:
        raise ValueError("无效的用例类型")

    case = ApiTestCase(
        project_id=int(payload["project_id"]),
        environment_id=int(payload["environment_id"]),
        service=str(payload["service"]).strip(),
        name=str(payload["name"]).strip(),
        api_path=str(payload["api_path"]).strip(),
        method=_normalize_method(str(payload.get("method") or "GET")),
        request_headers=payload.get("request_headers"),
        request_params=payload.get("request_params"),
        request_body=payload.get("request_body"),
        expected_status=int(payload.get("expected_status") or 200),
        expected_response=payload.get("expected_response"),
        response_assert_mode=str(payload.get("response_assert_mode") or "text").strip() or "text",
        response_assert_rules=payload.get("response_assert_rules"),
        case_type=case_type,
        endpoint_id=(str(payload["endpoint_id"]).strip() if payload.get("endpoint_id") else None),
        status="active",
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return get_api_test_case(db, case.id)


def _sample_value(data_type: str) -> object:
    lower = (data_type or "").lower()
    if "int" in lower or "long" in lower or "number" in lower:
        return 0
    if "bool" in lower:
        return False
    if "array" in lower or "list" in lower:
        return []
    if "object" in lower or "dict" in lower:
        return {}
    return ""


def _build_request_params_json(parameters: list[dict] | None) -> str | None:
    query: dict[str, object] = {}
    path: dict[str, object] = {}
    for param in parameters or []:
        name = str(param.get("name") or "").strip()
        if not name:
            continue
        sample = _sample_value(str(param.get("data_type") or ""))
        if param.get("in") == "query":
            query[name] = sample
        elif param.get("in") == "path":
            path[name] = sample
    if not query and not path:
        return None
    return json.dumps({"query": query, "path": path}, ensure_ascii=False, indent=2)


def _build_request_body_json(parameters: list[dict] | None) -> str | None:
    body_params = [param for param in (parameters or []) if param.get("in") == "body"]
    if not body_params:
        return None
    if len(body_params) == 1:
        param = body_params[0]
        if param.get("children"):
            sample = {
                str(child.get("name") or ""): _sample_value(str(child.get("data_type") or ""))
                for child in param.get("children") or []
                if child.get("name")
            }
            return json.dumps(sample, ensure_ascii=False, indent=2)
        return json.dumps(_sample_value(str(param.get("data_type") or "")), ensure_ascii=False, indent=2)
    sample = {
        str(param.get("name") or ""): _sample_value(str(param.get("data_type") or ""))
        for param in body_params
        if param.get("name")
    }
    return json.dumps(sample, ensure_ascii=False, indent=2)


def list_api_test_cases_by_endpoint(
    db: Session,
    endpoint_id: str,
    *,
    status: str = "active",
) -> list[dict]:
    result = list_api_test_cases(
        db,
        endpoint_id=endpoint_id,
        status=status,
        page=1,
        page_size=500,
    )
    return result["items"]


def _map_llm_case_type(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "smoke"
    if text in LLM_CASE_TYPE_MAP:
        return LLM_CASE_TYPE_MAP[text]
    lowered = text.lower()
    if lowered in VALID_CASE_TYPES:
        return lowered
    if "鉴权" in text or "授权" in text:
        return "custom"
    if "边界" in text or "必填" in text or "校验" in text:
        return "boundary"
    if "回归" in text:
        return "regression"
    return "smoke"


def _json_text(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _build_request_storage(
    *,
    method: str,
    headers: dict | None,
    request_data: object | None,
) -> tuple[str | None, str | None, str | None]:
    headers_obj = headers if isinstance(headers, dict) else {}
    request_headers = json.dumps(headers_obj, ensure_ascii=False, indent=2) if headers_obj else None

    params_obj: dict[str, object] = {}
    if method in {"GET", "HEAD", "DELETE"}:
        if isinstance(request_data, dict) and request_data:
            params_obj["query"] = request_data
        request_params = json.dumps(params_obj, ensure_ascii=False, indent=2) if params_obj else None
        return request_headers, request_params, None

    request_body = _json_text(request_data)
    request_params = json.dumps(params_obj, ensure_ascii=False, indent=2) if params_obj else None
    return request_headers, request_params, request_body


def _build_endpoint_prompt_context(payload: dict) -> str:
    context = {
        "method": payload.get("method"),
        "path": payload.get("api_path"),
        "summary": payload.get("summary"),
        "parameters": payload.get("parameters") or [],
        "expected_status": payload.get("expected_status", 200),
    }
    return json.dumps(context, ensure_ascii=False, indent=2)


def _normalize_generated_case_name(name: str, description: str = "") -> str:
    text = (name or "").strip()
    if not text:
        text = (description or "").strip()
    if not text:
        return "接口用例"

    text = re.sub(r"[（(].*[）)]$", "", text).strip()
    text = re.sub(r"^缺少必填字段", "缺", text)
    text = re.sub(r"^缺少必填参数", "缺", text)
    text = re.sub(r"^缺少必填", "缺", text)
    text = re.sub(r"^缺少", "缺", text)
    text = re.sub(r"^不携带", "无", text)
    text = re.sub(r"^未携带", "无", text)
    text = re.sub(r"^未带", "无", text)
    text = re.sub(r"认证信息$", "Token", text)
    text = re.sub(r"鉴权信息$", "Token", text)
    text = re.sub(r"\s+", " ", text)

    max_len = 28
    if len(text) > max_len:
        text = text[:max_len].rstrip("，,、 ") + "…"

    return text or "接口用例"


def _map_llm_test_case_to_create_payload(tc: dict, payload: dict, *, endpoint_id: str) -> dict:
    method = _normalize_method(str(tc.get("method") or payload.get("method") or "GET"))
    headers = tc.get("headers") if isinstance(tc.get("headers"), dict) else {}
    request_headers, request_params, request_body = _build_request_storage(
        method=method,
        headers=headers,
        request_data=tc.get("requestData"),
    )
    name = _normalize_generated_case_name(
        str(tc.get("name") or tc.get("id") or ""),
        str(tc.get("description") or ""),
    )

    return {
        "project_id": int(payload["project_id"]),
        "environment_id": int(payload["environment_id"]),
        "service": str(payload["service"]).strip(),
        "name": name,
        "api_path": str(tc.get("apiUrl") or payload.get("api_path") or "").strip(),
        "method": method,
        "request_headers": request_headers,
        "request_params": request_params,
        "request_body": request_body,
        "expected_status": int(tc.get("expectedStatusCode") or payload.get("expected_status") or 200),
        "expected_response": _json_text(tc.get("expectedResponse")),
        "case_type": _map_llm_case_type(str(tc.get("caseType") or "")),
        "endpoint_id": endpoint_id,
    }


async def _generate_cases_via_llm(db: Session, payload: dict, *, endpoint_id: str) -> list[dict]:
    prompt = get_prompt_template_for_type(db, "接口用例")
    llm_config = get_active_llm_config(db)
    user_content = _build_endpoint_prompt_context(payload)
    output_budget = suggest_output_tokens(llm_config.context_limit)

    base_messages = [
        {"role": "system", "content": prompt.content},
        {"role": "user", "content": user_content},
    ]
    retry_messages = [
        *base_messages,
        {
            "role": "user",
            "content": (
                "请重新生成。务必只返回一个 JSON 对象，包含 testCases 数组；"
                "不要 Markdown 代码块，不要解释文字。"
            ),
        },
    ]

    last_error: ValueError | None = None
    last_preview = ""

    for attempt, messages in enumerate((base_messages, retry_messages)):
        use_json_mode = attempt == 0
        try:
            result = await call_chat_completion(
                api_url=llm_config.api_url,
                api_key=llm_config.api_key,
                model_name=llm_config.model_name,
                messages=messages,
                temperature=0.1 if attempt else 0.2,
                max_tokens=output_budget,
                timeout=120.0,
                context_limit=llm_config.context_limit,
                response_format={"type": "json_object"} if use_json_mode else None,
            )
        except HTTPException:
            if attempt == 0:
                continue
            raise

        last_preview = (result.get("full_text") or result.get("content") or "")[:300]
        try:
            parsed = extract_test_cases_payload(result.get("content"), result.get("full_text"))
        except ValueError as exc:
            last_error = exc
            logger.warning(
                "api_case_llm_parse_failed attempt=%s preview=%s",
                attempt + 1,
                last_preview.replace("\n", "\\n"),
            )
            continue

        raw_cases = parsed.get("testCases")
        if not isinstance(raw_cases, list) or not raw_cases:
            last_error = ValueError("missing testCases")
            continue

        created_items: list[dict] = []
        for item in raw_cases:
            if not isinstance(item, dict):
                continue
            create_payload = _map_llm_test_case_to_create_payload(item, payload, endpoint_id=endpoint_id)
            if not create_payload["api_path"]:
                continue
            created_items.append(create_api_test_case(db, create_payload))

        if created_items:
            return created_items

        last_error = ValueError("empty testCases after mapping")

    detail = f"LLM 返回格式无效，无法解析 testCases：{last_error or 'unknown'}"
    if last_preview:
        detail = f"{detail}（响应摘要：{last_preview}）"
    raise HTTPException(status_code=502, detail=detail)


async def generate_api_test_cases_from_endpoint(db: Session, payload: dict) -> dict:
    endpoint_id = str(payload.get("endpoint_id") or "").strip()
    if not endpoint_id:
        raise ValueError("endpoint_id 不能为空")

    overwrite = bool(payload.get("overwrite"))
    existing = list_api_test_cases_by_endpoint(db, endpoint_id, status="active")
    if existing and not overwrite:
        return {"items": existing, "created": 0, "overwritten": 0}

    overwritten = 0
    if existing and overwrite:
        for item in existing:
            soft_delete_api_test_case(db, int(item["id"]))
        overwritten = len(existing)

    created_items = await _generate_cases_via_llm(db, payload, endpoint_id=endpoint_id)
    active_items = list_api_test_cases_by_endpoint(db, endpoint_id, status="active")
    return {
        "items": active_items,
        "created": len(created_items),
        "overwritten": overwritten,
    }

def update_api_test_case(db: Session, case_id: int, payload: dict) -> dict:
    case = db.query(ApiTestCase).filter(ApiTestCase.id == case_id).first()
    if not case:
        raise ValueError("用例不存在")

    if payload.get("project_id") is not None:
        case.project_id = int(payload["project_id"])
    if payload.get("environment_id") is not None:
        case.environment_id = int(payload["environment_id"])
    if payload.get("service") is not None:
        case.service = str(payload["service"]).strip()
    if payload.get("name") is not None:
        case.name = str(payload["name"]).strip()
    if payload.get("api_path") is not None:
        case.api_path = str(payload["api_path"]).strip()
    if payload.get("method") is not None:
        case.method = _normalize_method(str(payload["method"]))
    if "request_headers" in payload:
        case.request_headers = payload.get("request_headers")
    if "request_params" in payload:
        case.request_params = payload.get("request_params")
    if "request_body" in payload:
        case.request_body = payload.get("request_body")
    if payload.get("expected_status") is not None:
        case.expected_status = int(payload["expected_status"])
    if "expected_response" in payload:
        case.expected_response = payload.get("expected_response")
    if payload.get("response_assert_mode") is not None:
        case.response_assert_mode = str(payload["response_assert_mode"]).strip() or "text"
    if "response_assert_rules" in payload:
        case.response_assert_rules = payload.get("response_assert_rules")
    if payload.get("case_type") is not None:
        case_type = str(payload["case_type"]).strip().lower()
        if case_type not in VALID_CASE_TYPES:
            raise ValueError("无效的用例类型")
        case.case_type = case_type
    if "endpoint_id" in payload:
        endpoint_id = payload.get("endpoint_id")
        case.endpoint_id = str(endpoint_id).strip() if endpoint_id else None

    db.commit()
    db.refresh(case)
    return get_api_test_case(db, case.id)


def soft_delete_api_test_case(db: Session, case_id: int) -> None:
    case = db.query(ApiTestCase).filter(ApiTestCase.id == case_id).first()
    if not case:
        raise ValueError("用例不存在")
    if case.status == "deleted":
        return
    case.status = "deleted"
    case.deleted_at = datetime.utcnow()
    db.commit()


def hard_delete_api_test_case(db: Session, case_id: int) -> None:
    case = db.query(ApiTestCase).filter(ApiTestCase.id == case_id).first()
    if not case:
        raise ValueError("用例不存在")
    if case.status != "deleted":
        raise ValueError("仅已删除的用例可永久删除")
    db.delete(case)
    db.commit()


def batch_delete_api_test_cases(db: Session, case_ids: list[int]) -> dict:
    if not case_ids:
        raise ValueError("请选择至少一条用例")
    unique_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in case_ids:
        case_id = int(raw_id)
        if case_id <= 0 or case_id in seen:
            continue
        seen.add(case_id)
        unique_ids.append(case_id)
    if not unique_ids:
        raise ValueError("请选择至少一条用例")

    soft_deleted = 0
    hard_deleted = 0
    not_found = 0
    for case_id in unique_ids:
        case = db.query(ApiTestCase).filter(ApiTestCase.id == case_id).first()
        if not case:
            not_found += 1
            continue
        if case.status == "deleted":
            db.delete(case)
            hard_deleted += 1
        else:
            case.status = "deleted"
            case.deleted_at = datetime.utcnow()
            soft_deleted += 1
    db.commit()
    return {
        "soft_deleted": soft_deleted,
        "hard_deleted": hard_deleted,
        "not_found": not_found,
        "total": soft_deleted + hard_deleted,
    }


def restore_api_test_case(db: Session, case_id: int) -> dict:
    case = db.query(ApiTestCase).filter(ApiTestCase.id == case_id).first()
    if not case:
        raise ValueError("用例不存在")
    case.status = "active"
    case.deleted_at = None
    db.commit()
    db.refresh(case)
    return get_api_test_case(db, case.id)


def save_api_test_case_execution_result(db: Session, case_id: int, payload: dict) -> dict:
    case = db.query(ApiTestCase).filter(ApiTestCase.id == case_id).first()
    if not case:
        raise ValueError("用例不存在")

    case.last_exec_pass = bool(payload.get("passed"))
    status_code = payload.get("status_code")
    case.last_exec_status_code = int(status_code) if status_code is not None else None
    response = payload.get("response")
    case.last_exec_response = str(response) if response is not None else None
    detail = payload.get("detail")
    case.last_exec_detail = str(detail).strip() if detail else None
    case.last_exec_at = datetime.utcnow()

    db.commit()
    db.refresh(case)
    return get_api_test_case(db, case.id)

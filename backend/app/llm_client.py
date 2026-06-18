import json
import logging
import re
from typing import Any

import httpx
from fastapi import HTTPException

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
logger = logging.getLogger(__name__)

CONTEXT_FORMAT_OVERHEAD = 512
MIN_OUTPUT_TOKENS = 16
CHARS_PER_TOKEN_ESTIMATE = 3
DEFAULT_CONTEXT_LIMIT = 128000
TRUNCATE_SUFFIX = "\n...(输入已截断以适配上下文限制)"


def _chat_completions_url(api_url: str) -> str:
    base = (api_url or "").strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail="LLM API URL 不能为空")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _models_url(api_url: str) -> str:
    base = (api_url or "").strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail="LLM API URL 不能为空")
    if base.endswith("/models"):
        return base
    return f"{base}/models"


def _extract_message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts: list[str] = []
        for item in message:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part).strip()
    return ""


def _try_load_json(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _extract_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _escape_raw_newlines_in_strings(text: str) -> str:
    chars: list[str] = []
    in_string = False
    escape = False

    for char in text:
        if in_string:
            if escape:
                chars.append(char)
                escape = False
                continue
            if char == "\\":
                chars.append(char)
                escape = True
                continue
            if char == '"':
                chars.append(char)
                in_string = False
                continue
            if char == "\n":
                chars.append("\\n")
                continue
            if char == "\r":
                chars.append("\\r")
                continue
            if char == "\t":
                chars.append("\\t")
                continue
            chars.append(char)
            continue

        chars.append(char)
        if char == '"':
            in_string = True

    return "".join(chars)


def _strip_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _extract_assistant_content(message: Any) -> str:
    if isinstance(message, dict):
        for key in ("content", "reasoning_content", "text"):
            text = _extract_message_text(message.get(key))
            if text:
                return text
        return ""
    return _extract_message_text(message)


def _extract_full_assistant_text(message: Any) -> str:
    if isinstance(message, dict):
        parts: list[str] = []
        for key in ("content", "reasoning_content", "text"):
            text = _extract_message_text(message.get(key))
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return _extract_message_text(message)


def _strip_markdown_fence(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
    return re.sub(r"\s*```$", "", stripped).strip()


def estimate_text_tokens(text: str) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    return max(1, (len(normalized) + CHARS_PER_TOKEN_ESTIMATE - 1) // CHARS_PER_TOKEN_ESTIMATE)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 16
    for message in messages:
        role = str(message.get("role") or "")
        content = _extract_message_text(message.get("content"))
        total += estimate_text_tokens(role) + 4
        total += estimate_text_tokens(content)
    return total


def truncate_text_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return TRUNCATE_SUFFIX.strip()
    max_chars = max_tokens * CHARS_PER_TOKEN_ESTIMATE
    if len(text) <= max_chars:
        return text
    keep_chars = max(0, max_chars - len(TRUNCATE_SUFFIX))
    return f"{text[:keep_chars]}{TRUNCATE_SUFFIX}"


def resolve_output_token_budget(
    context_limit: int,
    *,
    requested_max_tokens: int,
    input_tokens: int,
) -> int:
    limit = max(MIN_OUTPUT_TOKENS * 2, int(context_limit or DEFAULT_CONTEXT_LIMIT))
    requested = max(MIN_OUTPUT_TOKENS, int(requested_max_tokens))
    available = limit - input_tokens - CONTEXT_FORMAT_OVERHEAD
    if available < MIN_OUTPUT_TOKENS:
        return MIN_OUTPUT_TOKENS
    return min(requested, available)


def suggest_output_tokens(context_limit: int, *, cap: int = 8192, ratio: float = 0.25, floor: int = 512) -> int:
    limit = max(MIN_OUTPUT_TOKENS * 2, int(context_limit or DEFAULT_CONTEXT_LIMIT))
    return min(cap, max(floor, int(limit * ratio)))


def fit_messages_to_context(
    messages: list[dict[str, Any]],
    *,
    context_limit: int,
    max_tokens: int,
) -> tuple[list[dict[str, Any]], int, int]:
    limit = max(MIN_OUTPUT_TOKENS * 2, int(context_limit or DEFAULT_CONTEXT_LIMIT))
    fitted: list[dict[str, Any]] = [dict(message) for message in messages]
    input_tokens = estimate_messages_tokens(fitted)
    effective_max_tokens = resolve_output_token_budget(
        limit,
        requested_max_tokens=max_tokens,
        input_tokens=input_tokens,
    )

    guard = 0
    while input_tokens + effective_max_tokens + CONTEXT_FORMAT_OVERHEAD > limit and guard < 20:
        guard += 1
        target_index = -1
        target_length = 0
        for index, message in enumerate(fitted):
            if message.get("role") not in {"user", "system"}:
                continue
            content = _extract_message_text(message.get("content"))
            if len(content) <= target_length:
                continue
            target_index = index
            target_length = len(content)

        if target_index < 0 or target_length <= 120:
            break

        message = fitted[target_index]
        current_content = _extract_message_text(message.get("content"))
        current_tokens = estimate_text_tokens(current_content)
        next_tokens = max(MIN_OUTPUT_TOKENS * 4, int(current_tokens * 0.75))
        message["content"] = truncate_text_to_tokens(current_content, next_tokens)
        input_tokens = estimate_messages_tokens(fitted)
        effective_max_tokens = resolve_output_token_budget(
            limit,
            requested_max_tokens=max_tokens,
            input_tokens=input_tokens,
        )

    if input_tokens + effective_max_tokens + CONTEXT_FORMAT_OVERHEAD > limit:
        raise HTTPException(
            status_code=400,
            detail=(
                f"输入内容过长，已超过上下文限制（约 {input_tokens} + {effective_max_tokens} > {limit} tokens）。"
                "请增大 LLM 配置中的上下文限制，或缩短提示词/接口参数。"
            ),
        )

    return fitted, effective_max_tokens, input_tokens


async def call_chat_completion(
    *,
    api_url: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: int = 1200,
    timeout: float = 90.0,
    require_content: bool = True,
    response_format: dict[str, str] | None = None,
    context_limit: int | None = None,
) -> dict:
    if not api_key:
        raise HTTPException(status_code=400, detail="LLM API Key 不能为空")
    if not model_name:
        raise HTTPException(status_code=400, detail="LLM 模型名称不能为空")

    url = _chat_completions_url(api_url)
    messages_to_send = messages
    effective_max_tokens = max(MIN_OUTPUT_TOKENS, int(max_tokens))
    if context_limit and context_limit > 0:
        messages_to_send, effective_max_tokens, input_tokens = fit_messages_to_context(
            messages,
            context_limit=context_limit,
            max_tokens=max_tokens,
        )
        if effective_max_tokens != max_tokens or messages_to_send != messages:
            logger.info(
                "llm_context_adjusted model=%s input_tokens=%s max_tokens=%s->%s context_limit=%s",
                model_name,
                input_tokens,
                max_tokens,
                effective_max_tokens,
                context_limit,
            )

    payload = {
        "model": model_name,
        "messages": messages_to_send,
        "stream": False,
        "temperature": temperature,
        "max_tokens": effective_max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or f"HTTP {exc.response.status_code}"
        raise HTTPException(status_code=502, detail=f"LLM 请求失败: {detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"LLM 连接失败: {exc}") from exc

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise HTTPException(status_code=502, detail="LLM 响应无 choices")

    first_choice = choices[0] or {}
    message = (first_choice.get("message") or {})
    content = _extract_assistant_content(message)
    full_text = _extract_full_assistant_text(message)
    if not content:
        finish_reason = str(first_choice.get("finish_reason") or "")
        if not require_content:
            return {
                "content": full_text,
                "full_text": full_text,
                "raw": data,
                "model": data.get("model") or model_name,
                "finish_reason": finish_reason,
            }
        if finish_reason == "length":
            detail = (
                "LLM 响应内容为空：输出 token 预算不足。"
                "若使用 gemini-2.5 等推理模型，请增大 max_tokens 或换用非推理模型做连通性测试。"
            )
        else:
            detail = f"LLM 响应内容为空（finish_reason={finish_reason or 'unknown'}）"
        raise HTTPException(status_code=502, detail=detail)

    return {
        "content": content,
        "full_text": full_text or content,
        "raw": data,
        "model": data.get("model") or model_name,
        "max_tokens": effective_max_tokens,
    }


def _find_model_match(model_name: str, models: list[str]) -> str | None:
    target = (model_name or "").strip()
    if not target:
        return None
    lower = target.lower()
    for item in models:
        if item.lower() == lower:
            return item
    for item in models:
        item_lower = item.lower()
        if lower in item_lower or item_lower in lower:
            return item
    return None


async def _test_connection_via_chat(
    *,
    api_url: str,
    api_key: str,
    model_name: str,
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
) -> dict:
    """Fallback：部分网关无 /models 接口时，用最小 chat 请求验证。"""
    result = await call_chat_completion(
        api_url=api_url,
        api_key=api_key,
        model_name=model_name,
        messages=[{"role": "user", "content": "OK"}],
        temperature=0,
        max_tokens=16,
        timeout=30.0,
        require_content=False,
        context_limit=context_limit,
    )
    content = (result.get("content") or "").strip()
    if content:
        message = f"连接成功（对话验证）：模型返回「{content[:80]}」"
    else:
        finish_reason = str(result.get("finish_reason") or "unknown")
        message = (
            f"连接成功（对话验证）：API 已响应（finish_reason={finish_reason}）。"
            "推理模型可能无可见正文，属正常情况。"
        )
    return {
        "ok": True,
        "message": message,
        "model": result["model"],
    }


async def test_openai_compatible_connection(
    *,
    api_url: str,
    api_key: str,
    model_name: str,
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
) -> dict:
    model_name = (model_name or "").strip()
    try:
        models = await fetch_openai_compatible_models(api_url=api_url, api_key=api_key, timeout=15.0)
    except HTTPException:
        return await _test_connection_via_chat(
            api_url=api_url,
            api_key=api_key,
            model_name=model_name,
            context_limit=context_limit,
        )

    matched = _find_model_match(model_name, models)
    if matched:
        return {
            "ok": True,
            "message": (
                f"连接成功：已验证 API URL 与 Key，模型「{matched}」可用"
                f"（提供商共 {len(models)} 个模型，快速检测未发起对话）"
            ),
            "model": matched,
        }

    # 模型不在列表中：可能名单不全，降级为最小对话探测
    chat_result = await _test_connection_via_chat(
        api_url=api_url,
        api_key=api_key,
        model_name=model_name,
        context_limit=context_limit,
    )
    chat_result["message"] = (
        f"{chat_result['message']} "
        f"（注意：该模型未出现在 /models 列表的 {len(models)} 个条目中，请确认名称是否正确）"
    )
    return chat_result


def _extract_balanced_json_array(text: str) -> str | None:
    start = text.find("[")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "[":
            depth += 1
            continue
        if char == "]":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _normalize_llm_json_dict(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return {"testCases": data}
    if isinstance(data, dict):
        if isinstance(data.get("testCases"), list):
            return data
        for key in ("test_cases", "cases", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return {"testCases": value}
        return data
    raise ValueError("invalid json payload from llm")


def extract_json_payload(content: str) -> dict[str, Any]:
    candidates: list[str] = []
    text = (content or "").strip()
    if not text:
        raise ValueError("empty content")

    block_match = JSON_BLOCK_RE.search(text)
    if block_match:
        candidates.append(block_match.group(1).strip())

    candidates.extend([text, _strip_markdown_fence(text)])

    seen: set[str] = set()
    for candidate_text in candidates:
        candidate_text = candidate_text.strip()
        if not candidate_text or candidate_text in seen:
            continue
        seen.add(candidate_text)

        direct = _try_load_json(candidate_text)
        if direct is not None:
            return _normalize_llm_json_dict(direct)

        for extractor in (_extract_balanced_json_object, _extract_balanced_json_array):
            fragment = extractor(candidate_text)
            if fragment is None:
                continue
            repaired_candidates = [
                fragment,
                _escape_raw_newlines_in_strings(fragment),
                _strip_trailing_commas(fragment),
                _strip_trailing_commas(_escape_raw_newlines_in_strings(fragment)),
            ]
            for repaired in repaired_candidates:
                parsed = _try_load_json(repaired)
                if parsed is not None:
                    return _normalize_llm_json_dict(parsed)

    logger.error("extract_json_payload_failed content_preview=%s", text[:1000])
    raise ValueError("no json object found")


def extract_test_cases_payload(*texts: str | None) -> dict[str, Any]:
    last_error: ValueError | None = None
    seen: set[str] = set()
    for raw in texts:
        text = (raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        try:
            return extract_json_payload(text)
        except ValueError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError("empty content")


async def fetch_openai_compatible_models(*, api_url: str, api_key: str, timeout: float = 30.0) -> list[str]:
    if not api_key:
        raise HTTPException(status_code=400, detail="LLM API Key 不能为空")

    url = _models_url(api_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or f"HTTP {exc.response.status_code}"
        raise HTTPException(status_code=502, detail=f"拉取模型列表失败: {detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"拉取模型列表失败: {exc}") from exc

    payload = response.json()
    data = payload.get("data")
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="模型列表响应格式无效")

    models: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "")).strip()
        if model_id:
            models.append(model_id)

    if not models:
        raise HTTPException(status_code=502, detail="提供商未返回任何模型")

    return sorted(set(models))

from __future__ import annotations

import re
from typing import Any

from app.fastapi_scanner import ApiEndpoint, ApiParameter, ApiResponse, _join_paths
from app.spring_java_models import (
    JavaTypeResolver,
    _extract_generic_arg,
    enrich_parameters_with_schema,
    enrich_response_with_schema,
)

METHOD_ANNOTATIONS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}

MAPPING_ANNOTATION_PATTERN = re.compile(
    r"^\s*@(?P<name>GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)"
    r"\s*(?:\((?P<args>[^)]*)\))?\s*$",
    re.MULTILINE,
)
CLASS_PATTERN = re.compile(
    r"(?P<header>(?:@[\w.]+(?:\s*\([^)]*\))?\s*)*)public\s+(?:final\s+)?class\s+(?P<class_name>\w+)",
    re.MULTILINE,
)
METHOD_SIGNATURE_PATTERN = re.compile(
    r"public\s+(?P<return_type>[\w.<>,\s\[\]?]+?)\s+(?P<method_name>\w+)\s*"
    r"\((?P<params>.*?)\)\s*(?:throws\s+[\w.\s,]+)?\s*\{",
    re.DOTALL,
)
REQUEST_MAPPING_PATTERN = re.compile(r"@RequestMapping\s*\((?P<args>[^)]*)\)", re.MULTILINE)
STRING_LITERAL_PATTERN = re.compile(r"""['"]([^'"]+)['"]""")
REQUEST_METHOD_PATTERN = re.compile(r"RequestMethod\.(\w+)")

PARAM_BINDING = {
    "RequestParam": "query",
    "PathVariable": "path",
    "RequestBody": "body",
    "RequestHeader": "header",
    "RequestPart": "formData",
    "RequestAttribute": "query",
    "ModelAttribute": "query",
}

SKIP_PARAM_TYPES = frozenset(
    {
        "HttpServletRequest",
        "HttpServletResponse",
        "HttpSession",
        "Principal",
        "Authentication",
        "BindingResult",
        "Model",
        "ModelMap",
        "RedirectAttributes",
        "UriComponentsBuilder",
        "WebRequest",
        "NativeWebRequest",
        "Errors",
        "Locale",
        "TimeZone",
        "InputStream",
        "OutputStream",
        "Reader",
        "Writer",
    }
)


def _strip_block_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)


def _annotation_paths(args: str | None) -> list[str]:
    if not args:
        return [""]
    text = args.strip()
    if not text:
        return [""]

    paths: list[str] = []
    for key in ("value", "path"):
        key_pattern = re.compile(rf"{key}\s*=\s*\{{([^}}]+)\}}")
        match = key_pattern.search(text)
        if match:
            paths.extend(STRING_LITERAL_PATTERN.findall(match.group(1)))
            if paths:
                return paths
        key_single = re.compile(rf"{key}\s*=\s*['\"]([^'\"]+)['\"]")
        match = key_single.search(text)
        if match:
            return [match.group(1)]

    quoted = STRING_LITERAL_PATTERN.findall(text)
    if quoted:
        return [quoted[0]]
    return [""]


def _annotation_methods(args: str | None, *, default: str | None) -> list[str]:
    if not args:
        return [default] if default else ["GET", "POST", "PUT", "DELETE", "PATCH"]
    methods = [item.upper() for item in REQUEST_METHOD_PATTERN.findall(args)]
    if methods:
        return methods
    if default:
        return [default]
    return ["GET", "POST", "PUT", "DELETE", "PATCH"]


def _class_prefix(header: str) -> str:
    mappings = list(REQUEST_MAPPING_PATTERN.finditer(header))
    if not mappings:
        return ""
    return _annotation_paths(mappings[-1].group("args"))[0]


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = item.strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _default_tag_name(class_name: str) -> str:
    cleaned = class_name.removesuffix("Controller").removesuffix("Endpoint")
    return cleaned or class_name or "default"


def _extract_tag_names_from_body(body: str) -> list[str]:
    tags: list[str] = []
    for pattern in (
        re.compile(
            r'(?:@io\.swagger\.v3\.oas\.annotations\.tags\.)?Tag\s*\(\s*name\s*=\s*["\']([^"\']+)["\']'
        ),
        re.compile(
            r'(?:@io\.swagger\.v3\.oas\.annotations\.tags\.)?Tag\s*\(\s*["\']([^"\']+)["\']\s*\)'
        ),
    ):
        for match in pattern.finditer(body):
            tag = match.group(1).strip()
            if tag:
                tags.append(tag)
    return tags


def _extract_tags_from_text(text: str) -> list[str]:
    tags: list[str] = []
    for block in _find_annotation_blocks(text, "Tags"):
        tags.extend(_extract_tag_names_from_body(block))

    tags.extend(_extract_tag_names_from_body(text))

    for pattern in (
        re.compile(r'@Api\s*\(\s*tags\s*=\s*["\']([^"\']+)["\']'),
        re.compile(r'@Api\s*\(\s*value\s*=\s*["\']([^"\']+)["\']'),
    ):
        match = pattern.search(text)
        if match:
            tags.append(match.group(1).strip())

    api_array = re.search(r'@Api\s*\(\s*tags\s*=\s*\{([^}]+)\}', text)
    if api_array:
        tags.extend(STRING_LITERAL_PATTERN.findall(api_array.group(1)))

    return _dedupe_strings(tags)


def _class_tags(header: str, class_name: str) -> list[str]:
    tags = _extract_tags_from_text(header)
    if tags:
        return tags
    return [_default_tag_name(class_name)]


def _operation_tags_from_before(before_text: str) -> list[str]:
    tags: list[str] = []
    for block in _find_annotation_blocks(before_text, "Operation"):
        tags_match = re.search(r"tags\s*=\s*\{([^}]*)\}", block, re.DOTALL)
        if tags_match:
            tags.extend(STRING_LITERAL_PATTERN.findall(tags_match.group(1)))
            continue
        single = _extract_java_string_arg(block, "tags")
        if single:
            tags.append(single)
    return _dedupe_strings(tags)


def _resolve_endpoint_tags(header: str, class_name: str, before_text: str) -> list[str]:
    class_tags = _class_tags(header, class_name)
    method_tags = _operation_tags_from_before(before_text)
    if method_tags:
        return _dedupe_strings(class_tags + method_tags)
    return class_tags


def _is_hidden_class(header: str) -> bool:
    return bool(re.search(r"@(Hidden|ApiIgnore)\b", header))


def _is_hidden_method(before_text: str) -> bool:
    scoped = before_text[-800:]
    if re.search(r"@(Hidden|ApiIgnore)\b", scoped):
        return True
    for block in _find_annotation_blocks(scoped, "Operation"):
        if re.search(r"hidden\s*=\s*true", block, re.IGNORECASE):
            return True
    return False


def _line_number(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


def _clean_java_type(type_text: str) -> str:
    cleaned = " ".join(type_text.split())
    cleaned = cleaned.removeprefix("final ").strip()
    return cleaned or "any"


def _schema_name_from_type(type_text: str) -> str | None:
    cleaned = _clean_java_type(type_text)
    if not cleaned or cleaned in {"String", "Integer", "Long", "Boolean", "int", "long", "boolean", "void"}:
        return None
    base = cleaned.split("<", 1)[0].strip()
    return base or None


def _split_param_tokens(params_text: str) -> list[str]:
    text = params_text.strip()
    if not text:
        return []

    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "<([":
            depth += 1
        elif char in ">)]":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_annotation_args(args: str) -> dict[str, Any]:
    text = (args or "").strip()
    parsed: dict[str, Any] = {}
    if not text:
        return parsed

    quoted = STRING_LITERAL_PATTERN.findall(text)
    if quoted and ("=" not in text and "required" not in text):
        parsed["value"] = quoted[0]
        return parsed

    for key in ("value", "name", "defaultValue"):
        match = re.search(rf"{key}\s*=\s*([^,)]+)", text)
        if not match:
            continue
        raw = match.group(1).strip()
        if raw.startswith('"') or raw.startswith("'"):
            quoted_value = STRING_LITERAL_PATTERN.findall(raw)
            if quoted_value:
                parsed[key] = quoted_value[0]
            else:
                parsed[key] = raw.strip("\"'")
        else:
            parsed[key] = raw

    required_match = re.search(r"required\s*=\s*(true|false)", text, re.IGNORECASE)
    if required_match:
        parsed["required"] = required_match.group(1).lower() == "true"

    if "value" not in parsed and "name" not in parsed and quoted:
        parsed["value"] = quoted[0]
    return parsed


def _extract_param_annotations(token: str) -> tuple[list[tuple[str, str]], str]:
    annotations: list[tuple[str, str]] = []
    rest = token.strip()
    while rest.startswith("@"):
        match = re.match(r"@(\w+)(?:\(([^)]*)\))?\s*", rest)
        if not match:
            break
        annotations.append((match.group(1), match.group(2) or ""))
        rest = rest[match.end() :].strip()
    return annotations, rest


def _parse_java_param(token: str, *, http_method: str) -> ApiParameter | None:
    annotations, rest = _extract_param_annotations(token)
    if not rest:
        return None

    match = re.match(r"(?P<type>[\w.<>,\s\[\]?]+)\s+(?P<name>\w+)\s*$", rest)
    if not match:
        return None

    data_type = _clean_java_type(match.group("type"))
    var_name = match.group("name")
    if data_type in SKIP_PARAM_TYPES or var_name in {"request", "response"}:
        return None

    in_type = "query"
    required = True
    description = ""
    schema_name = _schema_name_from_type(data_type)
    param_name = var_name

    binding_names = [name for name, _ in annotations if name in PARAM_BINDING]
    if binding_names:
        in_type = PARAM_BINDING[binding_names[-1]]
    elif http_method in {"POST", "PUT", "PATCH"} and not annotations:
        in_type = "body"

    if "MultipartFile" in data_type:
        in_type = "formData"

    for ann_name, ann_args in annotations:
        if ann_name == "Parameter":
            param_desc = _extract_java_string_arg(ann_args, "description")
            if param_desc:
                description = param_desc
            param_name_hint = _extract_java_string_arg(ann_args, "name")
            if param_name_hint:
                param_name = param_name_hint
            required_match = re.search(r"required\s*=\s*(true|false)", ann_args, re.IGNORECASE)
            if required_match:
                required = required_match.group(1).lower() == "true"
        if ann_name not in PARAM_BINDING:
            continue
        parsed_args = _parse_annotation_args(ann_args)
        if "value" in parsed_args:
            param_name = str(parsed_args["value"])
        elif "name" in parsed_args:
            param_name = str(parsed_args["name"])
        if "required" in parsed_args:
            required = bool(parsed_args["required"])
        if ann_name == "RequestBody" and "required" not in parsed_args:
            required = True

    if in_type == "body":
        return ApiParameter(
            name=param_name,
            in_="body",
            required=required,
            data_type="object",
            description=description,
            schema_name=schema_name,
        )

    return ApiParameter(
        name=param_name,
        in_=in_type,
        required=required,
        data_type=data_type,
        description=description,
        schema_name=schema_name if data_type not in {"String", "Integer", "Long", "Boolean", "int", "long", "boolean", "double", "float"} else None,
    )


def _parse_method_parameters(params_text: str, *, http_method: str) -> list[ApiParameter]:
    parameters: list[ApiParameter] = []
    for token in _split_param_tokens(params_text):
        parsed = _parse_java_param(token, http_method=http_method)
        if parsed:
            parameters.append(parsed)
    return parameters


def _extract_method_signature(class_body: str, start: int) -> tuple[str, str, str, str] | None:
    match = METHOD_SIGNATURE_PATTERN.search(class_body, start)
    if not match:
        return None
    return (
        _clean_java_type(match.group("return_type")),
        match.group("method_name"),
        match.group("params"),
        match.group(0),
    )


def _extract_java_string_arg(args: str, key: str) -> str:
    match = re.search(rf"{key}\s*=\s*", args)
    if not match:
        return ""
    rest = args[match.end() :].lstrip()
    if not rest:
        return ""
    quote = rest[0]
    if quote not in {'"', "'"}:
        return rest.split(",")[0].strip()
    escaped = False
    for index in range(1, len(rest)):
        char = rest[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == quote:
            return rest[1:index]
    return rest[1:]


def _extract_operation_meta(before_text: str) -> tuple[str, str]:
    summary = ""
    description = ""
    scoped = before_text[-800:]

    for block in _find_annotation_blocks(scoped, "Operation"):
        if not summary:
            summary = _extract_java_string_arg(block, "summary")
        if not description:
            description = _extract_java_string_arg(block, "description")

    if not summary:
        for pattern in (
            r"(@ApiOperation\s*\([^)]*\))",
            r"(//\s*@ApiOperation\s*\([^)]*\))",
        ):
            matches = list(re.finditer(pattern, scoped))
            if matches:
                args = matches[-1].group(1)
                summary = _extract_java_string_arg(args, "value")
                if not summary:
                    quoted = STRING_LITERAL_PATTERN.findall(args)
                    summary = quoted[0] if quoted else ""
                break

    if not description:
        for pattern in (
            r"(@ApiOperation\s*\([^)]*\))",
            r"(//\s*@ApiOperation\s*\([^)]*\))",
        ):
            matches = list(re.finditer(pattern, scoped))
            if matches:
                description = _extract_java_string_arg(matches[-1].group(1), "notes")
                if description:
                    break

    if not summary:
        javadoc_matches = list(re.finditer(r"/\*\*\s*(?:\n\s*\*\s*)?([^*\n][^\n]*)", scoped))
        if javadoc_matches:
            summary = javadoc_matches[-1].group(1).strip()

    return summary, description


def _parse_javadoc_content(content: str) -> tuple[str, str]:
    author = ""
    authored_at = ""
    author_match = re.search(r"@author\s+(\S+)", content, re.IGNORECASE)
    if author_match:
        author = author_match.group(1).strip()
    for pattern in (r"@date:?\s*([^\n*]+)", r"@since\s*([^\n*]+)"):
        date_match = re.search(pattern, content, re.IGNORECASE)
        if date_match:
            authored_at = date_match.group(1).strip()
            break
    return author, authored_at


def _extract_class_javadoc(source: str, class_name: str) -> tuple[str, str]:
    pattern = re.compile(
        rf"/\*\*(.*?)\*/\s*(?:@\w+(?:\([^)]*\))?\s*)*public\s+(?:final\s+)?class\s+{re.escape(class_name)}\b",
        re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        return "", ""
    return _parse_javadoc_content(match.group(1))


def _extract_method_javadoc(source: str, method_name: str) -> tuple[str, str]:
    pattern = re.compile(
        rf"/\*\*(.*?)\*/\s*(?:(?:@\w+\([^)]*\)|@\w+)\s*)*public\s+[\w.<>,\s\[\]?]+\s+{re.escape(method_name)}\s*\(",
        re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        return "", ""
    return _parse_javadoc_content(match.group(1))


def _wrapper_schema_from_return(return_type: str) -> str | None:
    cleaned = _clean_java_type(return_type)
    if cleaned.startswith("R<") or cleaned.startswith("Result<") or cleaned.startswith("Response<"):
        return cleaned.split("<", 1)[0].strip()
    schema_name = _schema_name_from_type(cleaned)
    return schema_name


def _parse_single_api_response(args: str) -> ApiResponse | None:
    code_match = re.search(r'(?:code|responseCode)\s*=\s*"?(\d{3})"?', args)
    if not code_match:
        return None
    status_code = code_match.group(1)
    description = (
        _extract_java_string_arg(args, "message")
        or _extract_java_string_arg(args, "description")
        or ""
    )
    schema_name = ""
    for pattern in (
        r"response\s*=\s*([\w.]+)\.class",
        r"implementation\s*=\s*([\w.]+)\.class",
    ):
        match = re.search(pattern, args)
        if match:
            schema_name = match.group(1).split(".")[-1]
            break
    return ApiResponse(
        status_code=status_code,
        description=description,
        data_type="object" if schema_name else "any",
        schema_name=schema_name or None,
    )


def _find_annotation_blocks(text: str, annotation: str) -> list[str]:
    blocks: list[str] = []
    needle = f"@{annotation}"
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            break
        paren_start = text.find("(", idx)
        if paren_start == -1:
            break
        depth = 0
        end_index = -1
        for pos in range(paren_start, len(text)):
            char = text[pos]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end_index = pos
                    break
        if end_index == -1:
            break
        blocks.append(text[paren_start + 1 : end_index])
        start = end_index + 1
    return blocks


def _extract_api_responses(
    before_text: str,
    class_header: str,
    return_type: str,
) -> list[ApiResponse]:
    scoped = f"{class_header}\n{before_text}"
    responses: list[ApiResponse] = []
    seen_codes: set[str] = set()

    for args in _find_annotation_blocks(scoped, "ApiResponse"):
        parsed = _parse_single_api_response(args)
        if parsed and parsed.status_code not in seen_codes:
            responses.append(parsed)
            seen_codes.add(parsed.status_code)

    if responses:
        return sorted(responses, key=lambda item: item.status_code)

    wrapper_schema = _wrapper_schema_from_return(return_type)
    schema_name = _schema_name_from_type(return_type)
    if wrapper_schema:
        schema_name = wrapper_schema
    responses.append(
        ApiResponse(
            status_code="200",
            description="成功",
            data_type="object" if schema_name else "any",
            schema_name=schema_name,
        )
    )
    seen_codes.add("200")

    if _has_swagger_annotations(scoped) or wrapper_schema:
        for status_code, description in (
            ("401", "Unauthorized"),
            ("404", "Not Found"),
            ("500", "Internal Server Error"),
        ):
            if status_code in seen_codes:
                continue
            responses.append(
                ApiResponse(
                    status_code=status_code,
                    description=description,
                    data_type="any",
                    schema_name=None,
                )
            )
            seen_codes.add(status_code)

    return responses


def _has_swagger_annotations(*texts: str) -> bool:
    markers = ("@ApiOperation", "@Api(", "@ApiResponses", "@ApiResponse", "@Operation", "@Tag(")
    return any(marker in text for text in texts for marker in markers)


def _build_response(return_type: str) -> list[ApiResponse]:
    schema_name = _schema_name_from_type(return_type)
    if return_type == "void":
        return [ApiResponse(status_code="200", description="成功", data_type="void")]
    return [
        ApiResponse(
            status_code="200",
            description="成功",
            data_type="object" if schema_name else "any",
            schema_name=schema_name,
        )
    ]


def scan_spring_source(
    source: str,
    source_file: str,
    *,
    resolver: JavaTypeResolver | None = None,
) -> list[ApiEndpoint]:
    if "@RestController" not in source and "@Controller" not in source:
        return []
    if "@ControllerAdvice" in source:
        return []

    cleaned = _strip_block_comments(source)
    endpoints: list[ApiEndpoint] = []

    for class_match in CLASS_PATTERN.finditer(cleaned):
        header = class_match.group("header")
        class_name = class_match.group("class_name")
        if _is_hidden_class(header):
            continue
        class_start = class_match.end()
        next_class = CLASS_PATTERN.search(cleaned, class_start)
        class_end = next_class.start() if next_class else len(cleaned)
        class_body = cleaned[class_start:class_end]
        prefix = _class_prefix(header)
        class_author, class_authored_at = _extract_class_javadoc(source, class_name)

        prev_mapping_end = 0
        for mapping in MAPPING_ANNOTATION_PATTERN.finditer(class_body):
            ann_name = mapping.group("name")
            args = mapping.group("args")
            paths = _annotation_paths(args)
            if ann_name == "RequestMapping":
                methods = _annotation_methods(args, default=None)
            else:
                methods = [METHOD_ANNOTATIONS[ann_name]]

            mapping_start = mapping.start()
            before_text = class_body[prev_mapping_end:mapping_start]
            if _is_hidden_method(before_text):
                signature = _extract_method_signature(class_body, mapping.end())
                prev_mapping_end = (
                    METHOD_SIGNATURE_PATTERN.search(class_body, mapping.end()).end()
                    if signature
                    else mapping.end()
                )
                continue
            summary_hint, description_hint = _extract_operation_meta(before_text)
            endpoint_tags = _resolve_endpoint_tags(header, class_name, before_text)

            signature = _extract_method_signature(class_body, mapping.end())
            if signature:
                return_type, method_name, params_text, _ = signature
                sig_match = METHOD_SIGNATURE_PATTERN.search(class_body, mapping.end())
                prev_mapping_end = sig_match.end() if sig_match else mapping.end()
            else:
                return_type, method_name, params_text = "any", "unknown", ""
                prev_mapping_end = mapping.end()

            line = _line_number(cleaned, class_match.start() + mapping.start())
            summary = summary_hint or method_name
            method_author, method_authored_at = _extract_method_javadoc(source, method_name)
            author = method_author or class_author
            authored_at = method_authored_at or class_authored_at

            for path in paths:
                full_path = _join_paths(prefix, path)
                for method in methods:
                    parameters = enrich_parameters_with_schema(
                        _parse_method_parameters(params_text, http_method=method),
                        resolver=resolver,
                    )
                    if description_hint:
                        body_params = [item for item in parameters if item.in_ == "body"]
                        if body_params:
                            if not body_params[0].description:
                                body_params[0].description = description_hint
                        elif parameters:
                            if not parameters[0].description:
                                parameters[0].description = description_hint
                        elif summary == method_name:
                            summary = description_hint

                    has_body = any(item.in_ == "body" for item in parameters)
                    response_generic = _extract_generic_arg(return_type)
                    responses = [
                        enrich_response_with_schema(
                            item,
                            resolver=resolver,
                            generic_type=response_generic,
                        )
                        for item in _extract_api_responses(before_text, header, return_type)
                    ]
                    endpoints.append(
                        ApiEndpoint(
                            method=method,
                            path=full_path,
                            summary=summary,
                            tags=endpoint_tags,
                            request_content_type="application/json" if has_body or method in {"POST", "PUT", "PATCH"} else "",
                            response_content_type="application/json" if return_type != "void" else "*/*",
                            parameters=parameters,
                            responses=responses,
                            source_file=source_file.replace("\\", "/"),
                            source_line=line,
                            operation_id=f"{class_name}.{method_name}",
                            author=author,
                            authored_at=authored_at,
                        )
                    )

    return endpoints


def scan_spring_sources(
    files: dict[str, str],
    *,
    resolver: JavaTypeResolver | None = None,
) -> list[ApiEndpoint]:
    endpoints: list[ApiEndpoint] = []
    for file_path, source in files.items():
        if not file_path.endswith(".java"):
            continue
        endpoints.extend(scan_spring_source(source, file_path, resolver=resolver))
    dedup: dict[str, ApiEndpoint] = {}
    for endpoint in endpoints:
        dedup[endpoint.endpoint_id] = endpoint
    return sorted(dedup.values(), key=lambda item: (item.path, item.method))


def scan_spring_source_debug(source: str, source_file: str) -> dict[str, Any]:
    endpoints = scan_spring_source(source, source_file)
    return {
        "source_file": source_file,
        "endpoint_count": len(endpoints),
        "endpoints": [
            {
                "method": item.method,
                "path": item.path,
                "summary": item.summary,
                "parameters": [
                    {"name": param.name, "in": param.in_, "type": param.data_type}
                    for param in item.parameters
                ],
            }
            for item in endpoints[:20]
        ],
    }

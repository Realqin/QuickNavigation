from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
FASTAPI_PARAM_NAMES = frozenset({"Query", "Path", "Body", "Header", "Cookie", "Depends"})


@dataclass
class ApiParameter:
    name: str
    in_: str
    required: bool
    data_type: str
    description: str = ""
    schema_name: str | None = None
    children: list[ApiParameter] = field(default_factory=list)


@dataclass
class ApiResponse:
    status_code: str
    description: str = ""
    data_type: str = ""
    schema_name: str | None = None
    properties: list[ApiParameter] = field(default_factory=list)


@dataclass
class ApiEndpoint:
    method: str
    path: str
    summary: str
    tags: list[str]
    request_content_type: str
    response_content_type: str
    parameters: list[ApiParameter]
    responses: list[ApiResponse]
    source_file: str
    source_line: int
    operation_id: str
    author: str = ""
    authored_at: str = ""

    @property
    def endpoint_id(self) -> str:
        return f"{self.method.upper()} {self.path}"


def _literal_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _join_paths(prefix: str, route: str) -> str:
    left = (prefix or "").rstrip("/")
    right = (route or "").strip()
    if not right.startswith("/"):
        right = f"/{right}"
    if not left:
        return right or "/"
    return f"{left}{right}" if right != "/" else left or "/"


def _expr_name(node: ast.expr | None) -> str:
    if node is None:
        return "any"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _expr_name(node.value)
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.BinOp):
        return "any"
    return "any"


def _annotation_type(node: ast.expr | None) -> str:
    if node is None:
        return "any"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Subscript):
        base = _annotation_type(node.value)
        if isinstance(node.slice, ast.Tuple):
            parts = [_annotation_type(elt) for elt in node.slice.elts]
            return f"{base}[{', '.join(parts)}]"
        return f"{base}[{_annotation_type(node.slice)}]"
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return f"{_annotation_type(node.left)} | {_annotation_type(node.right)}"
    return "any"


def _call_kw(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _call_arg(call: ast.Call, index: int) -> ast.expr | None:
    if len(call.args) > index:
        return call.args[index]
    return None


def _decorator_route_info(decorator: ast.expr) -> tuple[str, str, dict[str, Any]] | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None
    method = func.attr.lower()
    if method not in HTTP_METHODS:
        return None
    route = _literal_str(_call_arg(decorator, 0)) or ""
    kwargs: dict[str, Any] = {}
    for kw in decorator.keywords:
        if kw.arg == "response_model":
            kwargs["response_model"] = _expr_name(kw.value)
        elif kw.arg == "summary":
            kwargs["summary"] = _literal_str(kw.value) or ""
        elif kw.arg == "tags":
            if isinstance(kw.value, (ast.List, ast.Tuple)):
                kwargs["tags"] = [
                    item.value
                    for item in kw.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                ]
        elif kw.arg == "status_code":
            kwargs["status_code"] = _literal_str(kw.value) or str(
                kw.value.value if isinstance(kw.value, ast.Constant) else 200
            )
    return method.upper(), route, kwargs


def _parse_default_param(arg: ast.arg, default: ast.expr | None) -> ApiParameter | None:
    if not arg.arg or arg.arg in {"self", "cls", "request", "db"}:
        return None
    param_type = "query"
    required = default is None
    data_type = _annotation_type(arg.annotation)
    description = ""
    schema_name = None

    if isinstance(default, ast.Call) and isinstance(default.func, ast.Name):
        if default.func.id in FASTAPI_PARAM_NAMES:
            param_type = default.func.id.lower()
            if param_type == "body":
                param_type = "body"
            elif param_type == "header":
                param_type = "header"
            elif param_type == "cookie":
                param_type = "cookie"
            required = False
            for kw in default.keywords:
                if kw.arg == "default" and isinstance(kw.value, ast.Constant) and kw.value.value is ...:
                    required = True
                elif kw.arg == "description":
                    description = _literal_str(kw.value) or ""
            if _call_arg(default, 0) is not None and isinstance(_call_arg(default, 0), ast.Constant):
                if _call_arg(default, 0).value is ...:  # type: ignore[union-attr]
                    required = True
        elif default.func.id == "Depends":
            return None

    if param_type == "body":
        schema_name = data_type if data_type not in {"any", "dict"} else None
        return ApiParameter(
            name=arg.arg,
            in_="body",
            required=required,
            data_type="object",
            description=description,
            schema_name=schema_name,
        )

    return ApiParameter(
        name=arg.arg,
        in_=param_type,
        required=required,
        data_type=data_type,
        description=description,
        schema_name=schema_name if data_type not in {"str", "int", "float", "bool", "any"} else None,
    )


def _function_parameters(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ApiParameter]:
    params: list[ApiParameter] = []
    args = func.args.args
    defaults_offset = len(args) - len(func.args.defaults)
    for index, arg in enumerate(args):
        default_index = index - defaults_offset
        default = func.args.defaults[default_index] if default_index >= 0 else None
        parsed = _parse_default_param(arg, default)
        if parsed:
            params.append(parsed)
    return params


def _doc_summary(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    if not func.body or not isinstance(func.body[0], ast.Expr):
        return ""
    value = func.body[0].value
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        return ""
    lines = [line.strip() for line in value.value.strip().splitlines() if line.strip()]
    return lines[0] if lines else ""


class FastApiModuleScanner(ast.NodeVisitor):
    def __init__(self, source_file: str) -> None:
        self.source_file = source_file.replace("\\", "/")
        self.router_prefixes: dict[str, str] = {}
        self.endpoints: list[ApiEndpoint] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return
        target = node.targets[0].id
        if not isinstance(node.value, ast.Call):
            return
        func = node.value.func
        if isinstance(func, ast.Attribute) and func.attr == "APIRouter":
            prefix = _literal_str(_call_kw(node.value, "prefix")) or ""
            tags_kw = _call_kw(node.value, "tags")
            tags: list[str] = []
            if isinstance(tags_kw, (ast.List, ast.Tuple)):
                tags = [
                    item.value
                    for item in tags_kw.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                ]
            self.router_prefixes[target] = prefix
            if tags:
                self.router_prefixes[f"{target}__tags"] = ",".join(tags)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scan_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scan_function(node)

    def _scan_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            info = _decorator_route_info(decorator)
            if not info:
                continue
            method, route, kwargs = info
            router_name = ""
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                if isinstance(decorator.func.value, ast.Name):
                    router_name = decorator.func.value.id
            prefix = self.router_prefixes.get(router_name, "")
            path = _join_paths(prefix, route)
            tags = list(kwargs.get("tags") or [])
            if not tags and router_name:
                raw_tags = self.router_prefixes.get(f"{router_name}__tags", "")
                if raw_tags:
                    tags = raw_tags.split(",")
            if not tags:
                tags = [_tag_from_path(path)]
            response_model = kwargs.get("response_model")
            status_code = str(kwargs.get("status_code") or "200")
            parameters = _function_parameters(node)
            request_content_type = "application/json" if any(p.in_ == "body" for p in parameters) else ""
            response_content_type = "application/json" if response_model else "*/*"
            responses = [
                ApiResponse(
                    status_code=status_code,
                    description="成功",
                    data_type="object" if response_model else "any",
                    schema_name=response_model,
                )
            ]
            summary = kwargs.get("summary") or _doc_summary(node) or node.name
            self.endpoints.append(
                ApiEndpoint(
                    method=method,
                    path=path,
                    summary=summary,
                    tags=tags,
                    request_content_type=request_content_type,
                    response_content_type=response_content_type,
                    parameters=parameters,
                    responses=responses,
                    source_file=self.source_file,
                    source_line=node.lineno,
                    operation_id=node.name,
                )
            )


def _tag_from_path(path: str) -> str:
    parts = [part for part in path.split("/") if part and not part.startswith("{")]
    if not parts:
        return "default"
    if parts[0] in {"api", "v1", "v2", "v3"} and len(parts) > 1:
        return parts[1]
    return parts[0]


def scan_fastapi_source(source: str, source_file: str) -> list[ApiEndpoint]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    scanner = FastApiModuleScanner(source_file)
    scanner.visit(tree)
    return scanner.endpoints


def scan_fastapi_sources(files: dict[str, str]) -> list[ApiEndpoint]:
    endpoints: list[ApiEndpoint] = []
    for file_path, source in files.items():
        if not file_path.endswith(".py"):
            continue
        endpoints.extend(scan_fastapi_source(source, file_path))
    dedup: dict[str, ApiEndpoint] = {}
    for endpoint in endpoints:
        dedup[endpoint.endpoint_id] = endpoint
    return sorted(dedup.values(), key=lambda item: (item.path, item.method))


def endpoint_to_dict(endpoint: ApiEndpoint) -> dict[str, Any]:
    def param_dict(param: ApiParameter) -> dict[str, Any]:
        return {
            "name": param.name,
            "in": param.in_,
            "required": param.required,
            "data_type": param.data_type,
            "description": param.description,
            "schema_name": param.schema_name,
            "children": [param_dict(child) for child in param.children],
        }

    return {
        "id": endpoint.endpoint_id,
        "method": endpoint.method,
        "path": endpoint.path,
        "summary": endpoint.summary,
        "tags": endpoint.tags,
        "request_content_type": endpoint.request_content_type,
        "response_content_type": endpoint.response_content_type,
        "parameters": [param_dict(param) for param in endpoint.parameters],
        "responses": [
            {
                "status_code": response.status_code,
                "description": response.description,
                "data_type": response.data_type,
                "schema_name": response.schema_name,
                "properties": [param_dict(prop) for prop in response.properties],
            }
            for response in endpoint.responses
        ],
        "source": {
            "file": endpoint.source_file,
            "line": endpoint.source_line,
            "symbol": endpoint.operation_id,
            "author": endpoint.author or None,
            "authored_at": endpoint.authored_at or None,
        },
    }


def build_spec(endpoints: list[ApiEndpoint], *, meta: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    endpoint_dicts: dict[str, dict[str, Any]] = {}
    for endpoint in endpoints:
        endpoint_dicts[endpoint.endpoint_id] = endpoint_to_dict(endpoint)
    for endpoint in endpoints:
        tags = endpoint.tags or ["default"]
        payload = endpoint_dicts[endpoint.endpoint_id]
        for tag in tags:
            grouped.setdefault(tag, []).append(payload)
    for items in grouped.values():
        items.sort(key=lambda item: (item["path"], item["method"]))
    return {
        "spec_version": 1,
        "meta": meta,
        "groups": [{"tag": tag, "endpoints": grouped[tag]} for tag in sorted(grouped)],
        "endpoint_count": len(endpoints),
    }

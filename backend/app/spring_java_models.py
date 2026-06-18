from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from app.fastapi_scanner import ApiParameter

JAVA_CLASS_PATTERN = re.compile(
    r"(?:public\s+)?(?:abstract\s+)?(?:class)\s+(?P<class_name>\w+)"
    r"(?:<[^>]+>)?\s*(?:extends\s+(?P<parent>[\w.<>,\s]+?))?(?:\s+implements\s+[\w.<>,\s,]+)?\s*\{",
    re.MULTILINE,
)
JAVA_RECORD_PATTERN = re.compile(
    r"(?:public\s+)?record\s+(?P<class_name>\w+)\s*"
    r"(?:<[^>]+>)?\s*\((?P<params>[^)]*)\)\s*(?:implements\s+[\w.<>,\s,]+)?\s*\{?",
    re.DOTALL,
)
JAVA_FIELD_PATTERN = re.compile(
    r"(?P<prefix>(?:/\*\*.*?\*/\s*)?(?:(?:@\w+(?:\([^)]*\))?\s*)*))"
    r"(?:private|protected|public)\s+"
    r"(?P<type>[\w.<>,\s\[\]?]+?)\s+"
    r"(?P<name>\w+)(?:\s*=\s*[^;]+)?\s*;",
    re.DOTALL,
)
STRING_LITERAL_PATTERN = re.compile(r"""['"]([^'"]+)['"]""")
SKIP_FIELD_NAMES = frozenset({"serialVersionUID"})
SKIP_FIELD_TYPES = frozenset({"Logger", "log", "ObjectMapper"})
JAVA_GENERIC_PLACEHOLDERS = frozenset({"T", "E", "K", "V", "U"})
JAVA_DTO_PATH_HINTS = (
    "/req/",
    "/request/",
    "/dto/",
    "/vo/",
    "/model/",
    "/entity/",
    "/domain/",
    "/param/",
    "/pojo/",
    "/response/",
    "/resp/",
    "/api/",
    "/common/",
    "/bean/",
    "/form/",
    "/bo/",
    "/query/",
)
DTO_NAME_PREFIXES = ("Req", "Resp", "DTO", "Dto", "Vo", "VO", "Entity", "Model", "Param", "Query")
BLOCKED_JAVA_PATH_PARTS = ("/test/", "/tests/", "/target/", "/build/", "/out/", "/.git/")


def list_git_tracked_files(root: Path, *pathspecs: str) -> list[str] | None:
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", *pathspecs],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def should_index_java_path(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/").lower()
    if not normalized.endswith(".java"):
        return False
    return not any(part in normalized for part in BLOCKED_JAVA_PATH_PARTS)


def _is_likely_dto_path(rel: str) -> bool:
    lower = rel.replace("\\", "/").lower()
    if any(hint in lower for hint in JAVA_DTO_PATH_HINTS):
        return True
    name = rel.rsplit("/", 1)[-1]
    base = name[:-5] if name.endswith(".java") else name
    return any(base.startswith(prefix) for prefix in DTO_NAME_PREFIXES)


def _clean_java_type(type_text: str) -> str:
    cleaned = " ".join(type_text.split())
    cleaned = cleaned.removeprefix("final ").strip()
    return cleaned or "any"


def _schema_name_from_type(type_text: str) -> str | None:
    cleaned = _clean_java_type(type_text)
    if not cleaned or cleaned in {
        "String",
        "Integer",
        "Long",
        "Boolean",
        "Double",
        "Float",
        "int",
        "long",
        "boolean",
        "double",
        "float",
        "void",
        "Object",
        *JAVA_GENERIC_PLACEHOLDERS,
    }:
        return None
    base = cleaned.split("<", 1)[0].strip()
    return base or None


def _extract_generic_arg(type_text: str) -> str | None:
    cleaned = _clean_java_type(type_text)
    if "<" not in cleaned:
        return None
    start = cleaned.index("<") + 1
    depth = 0
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if char == "<":
            depth += 1
        elif char == ">":
            if depth == 0:
                return cleaned[start:index].strip() or None
            depth -= 1
    return None


def _apply_generic_type_to_properties(
    properties: list[ApiParameter],
    generic_type: str | None,
    *,
    resolver: JavaTypeResolver | None = None,
) -> list[ApiParameter]:
    if not generic_type:
        return properties

    generic_clean = _clean_java_type(generic_type)
    generic_schema = _schema_name_from_type(generic_clean)
    resolved: list[ApiParameter] = []
    for prop in properties:
        is_placeholder = prop.data_type in JAVA_GENERIC_PLACEHOLDERS or prop.schema_name in JAVA_GENERIC_PLACEHOLDERS
        if not is_placeholder:
            resolved.append(prop)
            continue
        children: list[ApiParameter] = []
        if generic_schema and resolver is not None:
            children = resolver.resolve(generic_schema)
        resolved.append(
            ApiParameter(
                name=prop.name,
                in_=prop.in_,
                required=prop.required,
                data_type=generic_clean,
                description=prop.description,
                schema_name=generic_schema,
                children=children,
            )
        )
    return resolved


def _parent_schema_name(parent_text: str | None) -> str | None:
    if not parent_text:
        return None
    cleaned = _clean_java_type(parent_text)
    return cleaned.split("<", 1)[0].strip() or None


def _extract_java_string_arg(args: str, key: str) -> str:
    match = re.search(rf"{key}\s*=\s*", args)
    if not match:
        return ""
    rest = args[match.end() :].lstrip()
    if not rest:
        return ""
    quote = rest[0]
    if quote not in {'"', "'"}:
        token = rest.split(",")[0].strip()
        return token
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


def _parse_field_annotations(prefix: str) -> tuple[str, bool | None]:
    description = ""
    required: bool | None = None

    for ann_match in re.finditer(r"@(\w+)\s*(?:\(([^)]*)\))?", prefix):
        ann_name = ann_match.group(1)
        ann_args = ann_match.group(2) or ""
        if ann_name == "ApiModelProperty":
            value = _extract_java_string_arg(ann_args, "value")
            if not value:
                quoted = STRING_LITERAL_PATTERN.findall(ann_args)
                value = quoted[0] if quoted else ""
            if value:
                description = value
            required_match = re.search(r"required\s*=\s*(true|false)", ann_args, re.IGNORECASE)
            if required_match:
                required = required_match.group(1).lower() == "true"
        elif ann_name == "Schema":
            schema_desc = _extract_java_string_arg(ann_args, "description") or _extract_java_string_arg(
                ann_args, "title"
            )
            if schema_desc:
                description = schema_desc
            if re.search(r"required\s*=\s*true", ann_args, re.IGNORECASE):
                required = True
            if re.search(r"requiredMode\s*=\s*RequiredMode\.REQUIRED", ann_args):
                required = True
        elif ann_name in {"NotNull", "NotBlank", "NotEmpty"}:
            required = True

    javadoc_match = re.search(r"/\*\*\s*(?:\n\s*\*\s*)?([^*\n][^\n]*)", prefix, re.DOTALL)
    if javadoc_match and not description:
        description = javadoc_match.group(1).strip()

    return description, required


def _build_field_parameter(
    *,
    field_name: str,
    field_type: str,
    prefix: str = "",
) -> ApiParameter | None:
    field_type = _clean_java_type(field_type)
    if field_name in SKIP_FIELD_NAMES:
        return None
    if field_type in SKIP_FIELD_TYPES:
        return None
    if field_name.isupper() and field_type in {"String", "int", "long"}:
        return None

    description, required_override = _parse_field_annotations(prefix)
    schema_name = _schema_name_from_type(field_type)
    data_type = field_type
    if schema_name and "<" in field_type:
        data_type = "array" if field_type.startswith(("List", "Set", "Collection")) else "object"

    return ApiParameter(
        name=field_name,
        in_="body",
        required=required_override if required_override is not None else False,
        data_type=data_type,
        description=description,
        schema_name=schema_name,
    )


def _parse_record_params(params_text: str) -> list[ApiParameter]:
    fields: list[ApiParameter] = []
    for token in _split_record_tokens(params_text):
        annotations, rest = _split_leading_annotations(token)
        match = re.match(r"(?P<type>[\w.<>,\s\[\]?]+)\s+(?P<name>\w+)\s*$", rest.strip())
        if not match:
            continue
        field = _build_field_parameter(
            field_name=match.group("name"),
            field_type=match.group("type"),
            prefix=annotations,
        )
        if field:
            fields.append(field)
    return fields


def _split_leading_annotations(token: str) -> tuple[str, str]:
    annotations: list[str] = []
    rest = token.strip()
    while rest.startswith("@"):
        match = re.match(r"@(\w+)(?:\(([^)]*)\))?\s*", rest)
        if not match:
            break
        annotations.append(match.group(0))
        rest = rest[match.end() :].strip()
    return "".join(annotations), rest


def _split_record_tokens(params_text: str) -> list[str]:
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


def _parse_class_fields(class_body: str) -> list[ApiParameter]:
    fields: list[ApiParameter] = []
    for match in JAVA_FIELD_PATTERN.finditer(class_body):
        field = _build_field_parameter(
            field_name=match.group("name"),
            field_type=match.group("type"),
            prefix=match.group("prefix"),
        )
        if field:
            fields.append(field)
    return fields


def _parse_class_block(
    source: str,
    class_name: str,
    *,
    type_index: dict[str, list[ApiParameter]] | None = None,
) -> list[ApiParameter]:
    cleaned = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    index = type_index or {}

    record_match = re.search(
        rf"(?:public\s+)?record\s+{re.escape(class_name)}\b[^{{]*\((?P<params>[^)]*)\)",
        cleaned,
        re.DOTALL,
    )
    if record_match:
        return _parse_record_params(record_match.group("params"))

    class_match = re.search(
        rf"(?:public\s+)?(?:abstract\s+)?class\s+{re.escape(class_name)}\b"
        r"(?:<[^>]+>)?\s*(?:extends\s+(?P<parent>[\w.<>,\s]+?))?(?:\s+implements\s+[\w.<>,\s,]+)?\s*\{",
        cleaned,
        re.DOTALL,
    )
    if not class_match:
        return []

    class_start = class_match.end()
    next_class = re.search(
        r"(?:public\s+)?(?:(?:abstract\s+)?class|record)\s+\w+",
        cleaned[class_start:],
    )
    class_end = class_start + next_class.start() if next_class else len(cleaned)
    class_body = cleaned[class_start:class_end]
    fields = _parse_class_fields(class_body)

    parent_name = _parent_schema_name(class_match.group("parent"))
    if not fields and parent_name:
        fields = list(index.get(parent_name, []))

    return fields


class _SourceLookup:
    def __init__(self, files: dict[str, str]):
        self.files = files
        self._by_filename: dict[str, str] = {}
        for path, source in files.items():
            filename = path.rsplit("/", 1)[-1]
            if filename.endswith(".java"):
                self._by_filename.setdefault(filename, source)


def _lookup_schema_fields(
    schema_name: str,
    type_index: dict[str, list[ApiParameter]],
    lookup: _SourceLookup,
) -> list[ApiParameter]:
    if schema_name in type_index:
        return list(type_index[schema_name])

    filename = f"{schema_name}.java"
    if filename in lookup._by_filename:
        fields = _parse_class_block(lookup._by_filename[filename], schema_name, type_index=type_index)
        if fields:
            type_index[schema_name] = fields
            return list(fields)

    for source in lookup.files.values():
        if re.search(rf"\b(?:class|record)\s+{re.escape(schema_name)}\b", source):
            fields = _parse_class_block(source, schema_name, type_index=type_index)
            if fields:
                type_index[schema_name] = fields
                return list(fields)

    return []


def build_java_type_index(files: dict[str, str]) -> dict[str, list[ApiParameter]]:
    return JavaTypeResolver.from_sources(files).type_index


class JavaTypeResolver:
    """Lazy Java model resolver: index paths first, parse DTO files on demand."""

    def __init__(self) -> None:
        self._cache: dict[str, list[ApiParameter]] = {}
        self._path_by_class: dict[str, str] = {}
        self._root: Path | None = None
        self._inline_sources: dict[str, str] = {}

    @classmethod
    def from_repo_root(
        cls,
        root: Path,
        *,
        inline_sources: dict[str, str] | None = None,
    ) -> JavaTypeResolver:
        resolver = cls()
        resolver._root = root
        if inline_sources:
            resolver._inline_sources = dict(inline_sources)

        tracked = list_git_tracked_files(root, "*.java")
        if tracked is not None:
            rel_paths = tracked
        else:
            rel_paths = [
                path.relative_to(root).as_posix()
                for path in root.rglob("*.java")
                if path.is_file()
            ]

        for rel in rel_paths:
            if not should_index_java_path(rel):
                continue
            class_name = rel.rsplit("/", 1)[-1][:-5]
            resolver._path_by_class.setdefault(class_name, rel)
        return resolver

    @classmethod
    def from_sources(cls, files: dict[str, str]) -> JavaTypeResolver:
        resolver = cls()
        resolver._inline_sources = dict(files)
        for rel in files:
            if not rel.endswith(".java"):
                continue
            class_name = rel.rsplit("/", 1)[-1][:-5]
            resolver._path_by_class.setdefault(class_name, rel)
        for class_name, rel in list(resolver._path_by_class.items()):
            if _is_likely_dto_path(rel):
                resolver._load_class(class_name, rel)
        return resolver

    @property
    def type_index(self) -> dict[str, list[ApiParameter]]:
        return self._cache

    @property
    def path_index_count(self) -> int:
        return len(self._path_by_class)

    def _warm_dto_cache(self) -> None:
        for class_name, rel in self._path_by_class.items():
            if _is_likely_dto_path(rel):
                self._load_class(class_name, rel)

    def _read_source(self, rel: str) -> str:
        if rel in self._inline_sources:
            return self._inline_sources[rel]
        if self._root is not None:
            return (self._root / rel).read_text(encoding="utf-8")
        return ""

    def _load_class(self, class_name: str, rel: str | None = None) -> list[ApiParameter]:
        if class_name in self._cache:
            return self._cache[class_name]
        rel_path = rel or self._path_by_class.get(class_name)
        if not rel_path:
            self._cache[class_name] = []
            return []
        try:
            source = self._read_source(rel_path)
        except OSError:
            self._cache[class_name] = []
            return []
        fields = _parse_class_block(source, class_name, type_index=self._cache)
        self._cache[class_name] = fields
        return fields

    def resolve(
        self,
        schema_name: str | None,
        *,
        depth: int = 0,
        max_depth: int = 2,
    ) -> list[ApiParameter]:
        if not schema_name or depth >= max_depth:
            return []

        fields = self._load_class(schema_name)
        if not fields:
            return []

        resolved: list[ApiParameter] = []
        for field in fields:
            children: list[ApiParameter] = []
            if field.schema_name:
                children = self.resolve(field.schema_name, depth=depth + 1, max_depth=max_depth)
            resolved.append(
                ApiParameter(
                    name=field.name,
                    in_=field.in_,
                    required=field.required,
                    data_type=field.data_type,
                    description=field.description,
                    schema_name=field.schema_name,
                    children=children,
                )
            )
        return resolved


def resolve_schema_properties(
    schema_name: str | None,
    type_index: dict[str, list[ApiParameter]],
    *,
    java_sources: dict[str, str] | None = None,
    resolver: JavaTypeResolver | None = None,
    depth: int = 0,
    max_depth: int = 2,
) -> list[ApiParameter]:
    if resolver is not None:
        return resolver.resolve(schema_name, depth=depth, max_depth=max_depth)
    if not schema_name or depth >= max_depth:
        return []

    lookup = _SourceLookup(java_sources or {})
    fields = _lookup_schema_fields(schema_name, type_index, lookup)
    if not fields:
        return []

    resolved: list[ApiParameter] = []
    for field in fields:
        children: list[ApiParameter] = []
        if field.schema_name:
            children = resolve_schema_properties(
                field.schema_name,
                type_index,
                java_sources=java_sources,
                depth=depth + 1,
                max_depth=max_depth,
            )
        resolved.append(
            ApiParameter(
                name=field.name,
                in_=field.in_,
                required=field.required,
                data_type=field.data_type,
                description=field.description,
                schema_name=field.schema_name,
                children=children,
            )
        )
    return resolved


def enrich_parameters_with_schema(
    parameters: list[ApiParameter],
    type_index: dict[str, list[ApiParameter]] | None = None,
    *,
    java_sources: dict[str, str] | None = None,
    resolver: JavaTypeResolver | None = None,
) -> list[ApiParameter]:
    enriched: list[ApiParameter] = []
    for param in parameters:
        if param.schema_name and param.in_ in {"body", "query", "formData"}:
            if resolver is not None:
                children = resolver.resolve(param.schema_name)
            else:
                children = resolve_schema_properties(
                    param.schema_name,
                    type_index or {},
                    java_sources=java_sources,
                )
            enriched.append(
                ApiParameter(
                    name=param.name,
                    in_=param.in_,
                    required=param.required,
                    data_type=param.data_type,
                    description=param.description,
                    schema_name=param.schema_name,
                    children=children,
                )
            )
        else:
            enriched.append(param)
    return enriched


def enrich_response_with_schema(
    response: Any,
    type_index: dict[str, list[ApiParameter]] | None = None,
    *,
    java_sources: dict[str, str] | None = None,
    resolver: JavaTypeResolver | None = None,
    generic_type: str | None = None,
) -> Any:
    from app.fastapi_scanner import ApiResponse

    if not isinstance(response, ApiResponse):
        return response
    if response.status_code != "200" or not response.schema_name:
        return response
    if resolver is not None:
        properties = resolver.resolve(response.schema_name)
    else:
        properties = resolve_schema_properties(
            response.schema_name,
            type_index or {},
            java_sources=java_sources,
        )
    properties = _apply_generic_type_to_properties(properties, generic_type, resolver=resolver)
    if not properties:
        return response
    return ApiResponse(
        status_code=response.status_code,
        description=response.description,
        data_type=response.data_type,
        schema_name=response.schema_name,
        properties=properties,
    )

from __future__ import annotations

import re
from pathlib import Path

from app.fastapi_scanner import ApiEndpoint, _join_paths

_GATEWAY_PATH = re.compile(r"Path=(/[^*\s]+)")
_GATEWAY_URI = re.compile(r"uri:\s*lb://(\S+)")
_ROUTE_ID_LINE = re.compile(r"^(\s*)-\s*id:\s*(\S+)\s*$")

_PROFILE_PRIORITY = (
    "application-k8s",
    "application-release",
    "application-prod",
    "application-sgptrelease",
    "application-gxbj",
    "application-gcbj",
    "application-dm",
)


def _profile_sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem.lower()
    for index, token in enumerate(_PROFILE_PRIORITY):
        if token in stem:
            return (index, stem)
    if "bak" in stem or "dev" in stem or "loc" in stem:
        return (100, stem)
    return (50, stem)


def _prefix_rank(prefix: str) -> tuple[int, int, str]:
    if prefix.startswith("/api/") and not prefix.startswith("/apiv1/"):
        return (0, len(prefix), prefix)
    if prefix.startswith("/apiv1/"):
        return (1, len(prefix), prefix)
    return (2, len(prefix), prefix)


def _normalize_service_key(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def module_from_source_file(source_file: str) -> str | None:
    for part in source_file.replace("\\", "/").split("/"):
        if part.startswith("hscp-"):
            return part
    return None


def parse_gateway_routes_from_text(text: str) -> dict[str, str]:
    routes: dict[str, str] = {}
    lines = text.splitlines()
    in_routes = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"\s*routes:\s*$", line):
            in_routes = True
            i += 1
            continue
        if not in_routes:
            i += 1
            continue
        id_match = _ROUTE_ID_LINE.match(line)
        if not id_match:
            if line and not line.startswith(" ") and not line.startswith("\t"):
                in_routes = False
            i += 1
            continue
        indent, route_id = id_match.group(1), id_match.group(2)
        route_path_prefix: str | None = None
        service_name = route_id
        j = i + 1
        while j < len(lines):
            next_match = _ROUTE_ID_LINE.match(lines[j])
            if next_match and next_match.group(1) == indent:
                break
            uri_match = _GATEWAY_URI.search(lines[j])
            if uri_match:
                service_name = uri_match.group(1)
            path_match = _GATEWAY_PATH.search(lines[j])
            if path_match:
                route_path_prefix = path_match.group(1).rstrip("/")
            j += 1
        if route_path_prefix:
            for raw_key in {route_id, service_name}:
                key = _normalize_service_key(raw_key)
                if key:
                    routes[key] = route_path_prefix
        i = j
    return routes


def discover_gateway_routes(repo_root: Path) -> dict[str, str]:
    merged: dict[str, str] = {}
    resource_dirs = [
        repo_root / "hscp-gateway" / "src" / "main" / "resources",
        *repo_root.glob("**/hscp-gateway/src/main/resources"),
    ]
    seen: set[str] = set()
    yml_files: list[Path] = []
    for resource_dir in resource_dirs:
        resolved = str(resource_dir.resolve())
        if resolved in seen or not resource_dir.is_dir():
            continue
        seen.add(resolved)
        yml_files.extend(resource_dir.glob("application*.yml"))
        yml_files.extend(resource_dir.glob("application*.yaml"))

    for yml in sorted(yml_files, key=_profile_sort_key):
        try:
            text = yml.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for key, prefix in parse_gateway_routes_from_text(text).items():
            existing = merged.get(key)
            if existing is None or _prefix_rank(prefix) < _prefix_rank(existing):
                merged[key] = prefix
    return merged


def _fallback_gateway_prefix(module: str) -> str | None:
    module_norm = _normalize_service_key(module)
    if not module_norm.startswith("hscp-"):
        return None
    suffix = module_norm.removeprefix("hscp-").strip()
    if not suffix:
        return None
    return f"/api/{suffix}"


def resolve_gateway_prefix(module: str, routes: dict[str, str]) -> str | None:
    if not module:
        return None
    module_norm = _normalize_service_key(module)
    candidates = [
        module_norm,
        f"{module_norm}-service",
        module_norm.replace("hscp-", "hscp_"),
    ]
    for candidate in candidates:
        if candidate in routes:
            return routes[candidate]
    for key, prefix in routes.items():
        if key == module_norm or key.startswith(f"{module_norm}-") or module_norm.startswith(key):
            return prefix
    return _fallback_gateway_prefix(module)


def apply_gateway_prefixes(
    endpoints: list[ApiEndpoint],
    routes: dict[str, str],
) -> list[ApiEndpoint]:
    if not routes:
        return endpoints
    for endpoint in endpoints:
        module = module_from_source_file(endpoint.source_file)
        if not module:
            continue
        prefix = resolve_gateway_prefix(module, routes)
        if not prefix:
            continue
        current = endpoint.path or "/"
        if current == prefix or current.startswith(f"{prefix}/"):
            continue
        endpoint.path = _join_paths(prefix, current)
    return endpoints

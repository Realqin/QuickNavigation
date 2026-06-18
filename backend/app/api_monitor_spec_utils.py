from __future__ import annotations

from typing import Any


def endpoint_key(endpoint: dict[str, Any]) -> str:
    endpoint_id = str(endpoint.get("id") or "").strip()
    if endpoint_id:
        return endpoint_id
    method = str(endpoint.get("method") or "").strip().upper()
    path = str(endpoint.get("path") or "").strip()
    return f"{method} {path}".strip()


def endpoint_tag(endpoint: dict[str, Any]) -> str:
    tags = endpoint.get("tags") or []
    if tags:
        return str(tags[0] or "default")
    return "default"


def iter_spec_endpoints(spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not spec:
        return []
    flat = spec.get("endpoints") or []
    if flat:
        return list(flat)
    endpoints: list[dict[str, Any]] = []
    for group in spec.get("groups") or []:
        endpoints.extend(group.get("endpoints") or [])
    return endpoints


def normalize_spec_for_storage(spec: dict[str, Any]) -> dict[str, Any]:
    """Store groups only; drop duplicated flat endpoint list."""
    normalized = {
        "spec_version": spec.get("spec_version", 1),
        "meta": spec.get("meta") or {},
        "groups": spec.get("groups") or [],
        "endpoint_count": int(spec.get("endpoint_count") or len(iter_spec_endpoints(spec))),
    }
    return normalized


def expand_spec_for_read(spec: dict[str, Any] | None) -> dict[str, Any]:
    """Return a read-friendly spec with a flattened endpoint list."""
    if not spec:
        return {
            "spec_version": 1,
            "meta": {},
            "groups": [],
            "endpoints": [],
            "endpoint_count": 0,
        }
    endpoints = iter_spec_endpoints(spec)
    return {
        "spec_version": spec.get("spec_version", 1),
        "meta": spec.get("meta") or {},
        "groups": spec.get("groups") or [],
        "endpoints": endpoints,
        "endpoint_count": int(spec.get("endpoint_count") or len(endpoints)),
    }

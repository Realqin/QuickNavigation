from pathlib import Path

from app.fastapi_scanner import ApiEndpoint, ApiParameter, ApiResponse
from app.gateway_route_utils import (
    apply_gateway_prefixes,
    discover_gateway_routes,
    parse_gateway_routes_from_text,
    resolve_gateway_prefix,
)


SAMPLE_GATEWAY_YML = """
spring:
  cloud:
    gateway:
      routes:
        - id: hscp-admin-service
          uri: lb://hscp-admin-service
          predicates:
            - Path=/api/admin/**
          filters:
            - StripPrefix=2
        - id: hscp-alarm
          uri: lb://hscp-alarm
          predicates:
            - Path=/api/alarm/**
          filters:
            - StripPrefix=2
"""


SAMPLE_GATEWAY_APiv1 = """
      routes:
        - id: hscp-external
          uri: lb://hscp-external
          predicates:
            - Path=/apiv1/external/**
          filters:
            - StripPrefix=2
"""


def test_parse_gateway_routes():
    routes = parse_gateway_routes_from_text(SAMPLE_GATEWAY_YML)
    assert routes["hscp-admin-service"] == "/api/admin"
    assert routes["hscp-alarm"] == "/api/alarm"


def test_parse_apiv1_external_route():
    routes = parse_gateway_routes_from_text(SAMPLE_GATEWAY_APiv1)
    assert routes["hscp-external"] == "/apiv1/external"


def test_fallback_prefix_for_unconfigured_module():
    routes = parse_gateway_routes_from_text(SAMPLE_GATEWAY_YML)
    assert resolve_gateway_prefix("hscp-fishery", routes) == "/api/fishery"


def test_prefer_api_over_apiv1_when_both_exist():
    from app.gateway_route_utils import _prefix_rank

    merged: dict[str, str] = {}
    for prefix in ("/apiv1/alarm", "/api/alarm"):
        existing = merged.get("hscp-alarm")
        if existing is None or _prefix_rank(prefix) < _prefix_rank(existing):
            merged["hscp-alarm"] = prefix
    assert merged["hscp-alarm"] == "/api/alarm"


def test_resolve_gateway_prefix_for_admin_module():
    routes = parse_gateway_routes_from_text(SAMPLE_GATEWAY_YML)
    assert resolve_gateway_prefix("hscp-admin", routes) == "/api/admin"


def test_apply_gateway_prefixes_to_endpoint():
    routes = parse_gateway_routes_from_text(SAMPLE_GATEWAY_YML)
    endpoint = ApiEndpoint(
        method="POST",
        path="/system/exportSysLog",
        summary="export",
        tags=["SystemAdminLog"],
        request_content_type="application/json",
        response_content_type="application/json",
        parameters=[],
        responses=[ApiResponse(status_code="200", description="OK")],
        source_file="hscp-admin/hscp-admin-service/src/main/java/example/SystemAdminLogController.java",
        source_line=1,
        operation_id="SystemAdminLogController.exportSysLog",
    )
    apply_gateway_prefixes([endpoint], routes)
    assert endpoint.path == "/api/admin/system/exportSysLog"


def test_discover_gateway_routes_from_repo_cache():
    root = Path("/data/api-repos/11_sub_1")
    if not root.is_dir():
        return
    routes = discover_gateway_routes(root)
    assert routes.get("hscp-admin-service") == "/api/admin"

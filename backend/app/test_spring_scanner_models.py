from app.spring_java_models import JavaTypeResolver, build_java_type_index
from app.spring_scanner import scan_spring_source

ROLE_CONTROLLER = '''
package com.example.role.controller;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/role")
@Api(tags = "角色管理")
public class RoleController {

    @PostMapping("/addRoleByTenant")
    @ApiOperation("添加角色")
    @ApiResponses({
        @ApiResponse(code = 200, message = "OK", response = R.class),
        @ApiResponse(code = 401, message = "Unauthorized"),
        @ApiResponse(code = 404, message = "Not Found"),
        @ApiResponse(code = 500, message = "Internal Server Error")
    })
    public R<Boolean> addRoleByTenant(@RequestBody ReqAddTenantRole reqAddTenantRole) {
        return null;
    }
}
'''

REQ_DTO = '''
package com.example.role.req;

public class ReqAddTenantRole {
    @ApiModelProperty(value = "角色ID")
    private Long id;
    private String roleName;
    private String roleDes;
    private Integer roleStatus;
}
'''

R_WRAPPER = '''
package com.example.common;

public class R<T> {
    private Integer code;
    private String msg;
    private T data;
}
'''

TEST_SOURCES = {
    "ReqAddTenantRole.java": REQ_DTO,
    "R.java": R_WRAPPER,
}


def _build_resolver() -> JavaTypeResolver:
    return JavaTypeResolver.from_sources(TEST_SOURCES)


WHITE_LIST_CONTROLLER = '''
package cn.com.highlander.hscp.alarm.controller;

@io.swagger.v3.oas.annotations.tags.Tag(name = "白名单操作")
@RestController
@RequestMapping("/whiteList")
public class WhiteListController {
    @PostMapping("/add")
    public R<Boolean> add() {
        return null;
    }
}
'''


FEIGN_ALARM_TEMPLATE = '''
/**
 * @description 报警模板对外接口
 */
@RestController
@RequestMapping("/feign/alarm/template")
public class FeignAlarmTemplateController {
    @GetMapping("/list")
    public R<List<Object>> list() {
        return null;
    }
}
'''


def test_javadoc_description_not_used_as_tag():
    endpoints = scan_spring_source(
        FEIGN_ALARM_TEMPLATE,
        "hscp-alarm/hscp-alarm-server/src/main/java/cn/com/highlander/hscp/alarm/controller/feignController/FeignAlarmTemplateController.java",
    )
    assert len(endpoints) == 1
    assert endpoints[0].tags == ["FeignAlarmTemplate"]


def test_default_tag_uses_class_name_not_module_path():
    controller = '''
@RestController
@RequestMapping("/alarm/effect/area")
public class TAlarmEffectAreaController {
    @GetMapping("/list")
    public R<Boolean> list() {
        return null;
    }
}
'''
    endpoints = scan_spring_source(
        controller,
        "hscp-alarm/hscp-alarm-server/src/main/java/cn/com/highlander/hscp/alarm/controller/TAlarmEffectAreaController.java",
    )
    assert endpoints[0].tags == ["TAlarmEffectArea"]


def test_operation_tags_merge_with_class_tags():
    controller = '''
@Tag(name = "报警关注")
@RestController
@RequestMapping("/follow")
public class FollowController {
    @Operation(summary = "查询", tags = {"报警关注分组"})
    @GetMapping("/list")
    public R<Boolean> list() {
        return null;
    }
}
'''
    endpoints = scan_spring_source(controller, "FollowController.java")
    assert endpoints[0].tags == ["报警关注", "报警关注分组"]


def test_hidden_operation_is_skipped():
    controller = '''
@RestController
@RequestMapping("/demo")
public class DemoController {
    @Hidden
    @GetMapping("/hidden")
    public R<Boolean> hidden() {
        return null;
    }

    @GetMapping("/visible")
    public R<Boolean> visible() {
        return null;
    }
}
'''
    endpoints = scan_spring_source(controller, "DemoController.java")
    assert len(endpoints) == 1
    assert endpoints[0].path.endswith("/visible")


def test_openapi3_tag_name():
    endpoints = scan_spring_source(
        WHITE_LIST_CONTROLLER,
        "hscp-alarm/hscp-alarm-server/src/main/java/cn/com/highlander/hscp/alarm/controller/WhiteListController.java",
    )
    assert len(endpoints) == 1
    assert endpoints[0].tags == ["白名单操作"]


REQ_DTO_SCHEMA = '''
public class ReqAddTenantRole {
    @Schema(description = "角色ID", requiredMode = RequiredMode.REQUIRED)
    private Long id;
    private String roleName;
}
'''


def test_schema_field_description():
    controller = '''
@RestController
@RequestMapping("/role")
public class RoleController {
    @PostMapping("/add")
    public R<Boolean> add(@RequestBody ReqAddTenantRole body) {
        return null;
    }
}
'''
    files = {"ReqAddTenantRole.java": REQ_DTO_SCHEMA}
    resolver = JavaTypeResolver.from_sources(files)
    endpoints = scan_spring_source(controller, "RoleController.java", resolver=resolver)
    body = endpoints[0].parameters[0]
    id_field = next(item for item in body.children if item.name == "id")
    assert id_field.description == "角色ID"
    assert id_field.required is True


def test_build_spec_supports_multiple_tags():
    from app.fastapi_scanner import ApiEndpoint, ApiParameter, ApiResponse, build_spec

    endpoint = ApiEndpoint(
        method="GET",
        path="/demo",
        summary="demo",
        tags=["A", "B"],
        request_content_type="",
        response_content_type="application/json",
        parameters=[],
        responses=[ApiResponse(status_code="200", description="OK")],
        source_file="Demo.java",
        source_line=1,
        operation_id="Demo.demo",
    )
    spec = build_spec([endpoint], meta={})
    tags = {group["tag"] for group in spec["groups"]}
    assert tags == {"A", "B"}
    assert spec["endpoint_count"] == 1


def test_add_role_by_tenant_uses_api_tag():
    endpoints = scan_spring_source(
        ROLE_CONTROLLER,
        "hscp-admin/hscp-admin-service/src/main/java/com/example/role/controller/RoleController.java",
        resolver=_build_resolver(),
    )
    endpoint = next(item for item in endpoints if item.path.endswith("/addRoleByTenant"))
    assert endpoint.tags == ["角色管理"]


def test_add_role_by_tenant_expands_body_fields():
    endpoints = scan_spring_source(
        ROLE_CONTROLLER,
        "hscp-admin/hscp-admin-service/src/main/java/com/example/role/controller/RoleController.java",
        resolver=_build_resolver(),
    )
    endpoint = next(item for item in endpoints if item.path.endswith("/addRoleByTenant"))
    assert endpoint.method == "POST"
    assert len(endpoint.parameters) == 1
    body = endpoint.parameters[0]
    assert body.name == "reqAddTenantRole"
    assert body.schema_name == "ReqAddTenantRole"
    assert body.required is True
    child_names = {item.name for item in body.children}
    assert child_names == {"id", "roleName", "roleDes", "roleStatus"}


def test_add_role_by_tenant_parses_response_codes():
    endpoints = scan_spring_source(
        ROLE_CONTROLLER,
        "hscp-admin/hscp-admin-service/src/main/java/com/example/role/controller/RoleController.java",
        resolver=_build_resolver(),
    )
    endpoint = next(item for item in endpoints if item.path.endswith("/addRoleByTenant"))
    status_codes = {item.status_code for item in endpoint.responses}
    assert status_codes == {"200", "401", "404", "500"}
    success = next(item for item in endpoint.responses if item.status_code == "200")
    field_map = {item.name: item.data_type for item in success.properties}
    assert field_map == {"code": "Integer", "msg": "String", "data": "Boolean"}


def test_req_dto_in_separate_module_path():
    controller = '''
@RestController
@RequestMapping("/sysrole")
public class SysRoleController {
    @PostMapping("/addRoleByTenant")
    public R<Boolean> addRoleByTenant(@RequestBody ReqAddTenantRole reqAddTenantRole) {
        return null;
    }
}
'''
    dto = '''
public class ReqAddTenantRole {
    private Long id;
    private String roleName;
    private String roleDes;
    private Integer roleStatus;
}
'''
    files = {
        "hscp-admin/hscp-admin-service/src/main/java/cn/com/highlander/hscp/admin/controller/SysRoleController.java": controller,
        "hscp-admin/hscp-admin-api/src/main/java/cn/com/highlander/hscp/admin/api/req/ReqAddTenantRole.java": dto,
    }
    resolver = JavaTypeResolver.from_sources(files)
    assert "ReqAddTenantRole" in resolver.type_index
    endpoints = scan_spring_source(
        controller,
        "hscp-admin/hscp-admin-service/src/main/java/cn/com/highlander/hscp/admin/controller/SysRoleController.java",
        resolver=resolver,
    )
    endpoint = next(item for item in endpoints if item.path.endswith("/addRoleByTenant"))
    assert len(endpoint.parameters[0].children) == 4


def test_build_java_type_index_compat():
    index = build_java_type_index(TEST_SOURCES)
    assert "ReqAddTenantRole" in index

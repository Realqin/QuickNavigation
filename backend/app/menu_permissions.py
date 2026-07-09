"""系统菜单权限树定义，前后端共用同一套 key。"""

from __future__ import annotations

from typing import Any

ALL_MENU_PERMISSION_KEYS: list[str] = [
    "home",
    "logs",
    "apiMonitor",
    "serviceMonitor",
    "connections",
    "apiCases",
    "llmConfigs",
    "prompts",
    "dict",
    "methodDatabase",
    "methodTerminal",
    "methodRedis",
    "methodMqtt",
    "methodKafka",
    "userManagement",
    "operationLogs",
]

MENU_PERMISSION_TREE: list[dict[str, Any]] = [
    {"key": "home", "title": "首页"},
    {"key": "logs", "title": "日志订阅"},
    {"key": "apiMonitor", "title": "接口调试"},
    {"key": "serviceMonitor", "title": "K8s连接（K8s）"},
    {"key": "connections", "title": "连接管理"},
    {"key": "apiCases", "title": "接口用例管理"},
    {
        "key": "configManagement",
        "title": "配置管理",
        "children": [
            {"key": "llmConfigs", "title": "LLM配置"},
            {"key": "prompts", "title": "提示词管理"},
            {"key": "dict", "title": "字典管理"},
            {"key": "userManagement", "title": "用户管理"},
        ],
    },
    {
        "key": "connectionMethods",
        "title": "连接方式 / 连接管理",
        "children": [
            {"key": "methodDatabase", "title": "MySQL/数据库"},
            {"key": "methodTerminal", "title": "终端模拟器"},
            {"key": "methodRedis", "title": "Redis"},
            {"key": "methodMqtt", "title": "MQTT"},
            {"key": "methodKafka", "title": "Kafka"},
        ],
    },
    {"key": "operationLogs", "title": "操作日志"},
]

PAGE_LABELS: dict[str, str] = {
    "home": "首页",
    "logs": "日志订阅",
    "apiMonitor": "接口调试",
    "serviceMonitor": "K8s连接",
    "connections": "连接管理",
    "apiCases": "接口用例管理",
    "llmConfigs": "LLM配置",
    "prompts": "提示词管理",
    "dict": "字典管理",
    "methodDatabase": "数据库",
    "methodTerminal": "Linux 终端",
    "methodRedis": "Redis",
    "methodMqtt": "MQTT",
    "methodKafka": "Kafka",
    "userManagement": "用户管理",
    "operationLogs": "操作日志",
}


def all_menu_keys() -> list[str]:
    return list(ALL_MENU_PERMISSION_KEYS)


def user_has_menu(user, menu_key: str) -> bool:
    if getattr(user, "is_admin", False):
        return True
    permissions = set(getattr(user, "menu_permissions", None) or [])
    return menu_key in permissions

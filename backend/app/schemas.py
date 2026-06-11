from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DictItemBase(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    sort_order: int = 0

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        allowed = {"project", "environment", "label", "connection_group"}
        if value not in allowed:
            raise ValueError(f"type 必须是 {', '.join(sorted(allowed))}")
        return value


class DictItemCreate(DictItemBase):
    pass


class DictItemUpdate(BaseModel):
    type: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    sort_order: int | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        allowed = {"project", "environment", "label", "connection_group"}
        if value not in allowed:
            raise ValueError(f"type 必须是 {', '.join(sorted(allowed))}")
        return value


class DictItemOut(BaseModel):
    id: int
    type: str
    name: str
    description: str | None
    sort_order: int
    is_system: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_item(cls, item: Any) -> "DictItemOut":
        return cls(
            id=item.id,
            type=item.dict_type,
            name=item.name,
            description=item.description,
            sort_order=item.sort_order,
            is_system=bool(getattr(item, "is_system", False)),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class SubLinkItem(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=512)
    is_reachable: bool | None = None
    last_checked_at: datetime | str | None = None


class ConnectionBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(default="", max_length=512)
    description: str | None = None
    projects: list[int] = Field(default_factory=list)
    environments: list[int] = Field(default_factory=list)
    type: int = Field(default=1)
    group_id: int | None = None
    is_shared: bool = False
    sort_order: int = 0
    icon: str | None = None
    sub_links: list[SubLinkItem] = Field(default_factory=list)
    host: str | None = Field(default=None, max_length=256)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    database_name: str | None = Field(default=None, max_length=128)

    @field_validator("sub_links", mode="before")
    @classmethod
    def normalize_sub_links(cls, value: Any) -> list:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        cleaned = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                url = str(item.get("url", "")).strip()
                if name and url:
                    cleaned.append(
                        {
                            "name": name,
                            "url": url,
                            "is_reachable": item.get("is_reachable"),
                            "last_checked_at": item.get("last_checked_at"),
                        }
                    )
        return cleaned

    @field_validator("projects", "environments", mode="before")
    @classmethod
    def normalize_id_list(cls, value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, (int, str)):
            value = [value]
        if isinstance(value, list):
            result: list[int] = []
            for item in value:
                if item is None or item == "":
                    continue
                result.append(int(item))
            return result
        return []

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: Any) -> int:
        if value is None or value == "":
            return 1
        if isinstance(value, str) and not value.isdigit():
            raise ValueError("type 必须是字典项 ID")
        return int(value)


class ConnectionCreate(ConnectionBase):
    group_id: int
    password: str | None = Field(default=None, max_length=512)

    @field_validator("group_id", mode="before")
    @classmethod
    def validate_group_id(cls, value: Any) -> int:
        if value is None or value == "":
            raise ValueError("请选择连接分组")
        return int(value)


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    url: str | None = Field(default=None, max_length=512)
    description: str | None = None
    projects: list[int] | None = None
    environments: list[int] | None = None
    type: int | None = None
    group_id: int | None = None
    is_shared: bool | None = None
    sort_order: int | None = None
    icon: str | None = None
    sub_links: list[SubLinkItem] | None = None
    host: str | None = Field(default=None, max_length=256)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    database_name: str | None = Field(default=None, max_length=128)

    @field_validator("projects", "environments", mode="before")
    @classmethod
    def normalize_id_list(cls, value: Any) -> list[int] | None:
        if value is None:
            return value
        if isinstance(value, (int, str)):
            value = [value]
        if isinstance(value, list):
            return [int(item) for item in value if item is not None and item != ""]
        return []

class ConnectionOut(ConnectionBase):
    id: int
    password_set: bool = False
    is_reachable: bool | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_connection(cls, conn: Any) -> "ConnectionOut":
        from app.services import connection_to_out_dict

        return cls.model_validate(connection_to_out_dict(conn))


class ConnectionTestRequest(BaseModel):
    type: int
    host: str = Field(min_length=1, max_length=256)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    database_name: str | None = Field(default=None, max_length=128)


class ConnectionTestOut(BaseModel):
    ok: bool
    message: str
    latency_ms: float | None = None


class ConnectionPingOut(BaseModel):
    id: int
    is_reachable: bool
    last_checked_at: datetime

    model_config = {"from_attributes": True}


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    scope: str
    items: list[ReorderItem]


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class HomeGroupOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    sort_order: int
    is_system: bool = False
    is_project_group: bool = False
    connections: list["ConnectionOut"] = Field(default_factory=list)


class HomeResponse(BaseModel):
    groups: list[HomeGroupOut]
    projects: list[DictItemOut]
    environments: list[DictItemOut]
    labels: list[DictItemOut]
    connection_groups: list[DictItemOut] = Field(default_factory=list)


class SubscriptionBase(BaseModel):
    enabled: bool = False
    github_repo: str | None = None
    github_branch: str | None = None
    github_events: list[str] | None = None
    db_filter: dict[str, Any] | None = None
    notify_homepage: bool = True


class SubscriptionCreate(SubscriptionBase):
    connection_id: int


class SubscriptionUpdate(BaseModel):
    enabled: bool | None = None
    github_repo: str | None = None
    github_branch: str | None = None
    github_events: list[str] | None = None
    db_filter: dict[str, Any] | None = None
    notify_homepage: bool | None = None
    link_enabled: dict[str, bool] | None = None


class GitlabSubscriptionLinkOut(BaseModel):
    link_key: str
    name: str
    url: str
    branch: str
    repo_path: str = ""
    enabled: bool
    link_kind: str = "gitlab"
    webhook_secret: str | None = None


class GitlabSubscriptionTreeOut(BaseModel):
    id: int
    connection_id: int
    connection_name: str
    connection_type_name: str | None = None
    project_display: str
    environment_display: str
    links: list[GitlabSubscriptionLinkOut]


class SubscriptionOut(SubscriptionBase):
    id: int
    connection_id: int
    webhook_secret: str
    webhook_url: str | None = None
    connection_name: str | None = None
    connection_url: str | None = None
    connection_type_name: str | None = None
    provider: str | None = None
    project_display: str | None = None
    environment_display: str | None = None
    branch_display: str | None = None
    repo_web_url: str | None = None
    repo_base_url: str | None = None
    projects: list[int] = Field(default_factory=list)
    environments: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActivityLogDiffOut(BaseModel):
    log_id: int
    commit_sha: str | None
    diff: str
    repo: str | None = None
    branch: str | None = None
    provider: str | None = None


class ActivityLogOut(BaseModel):
    id: int
    subscription_id: int | None
    connection_id: int | None
    project: str
    environment: str
    source_type: str
    title: str
    summary: str | None
    payload: dict[str, Any] | None
    author: str | None
    occurred_at: datetime
    is_read: bool

    model_config = {"from_attributes": True}


class DatabaseWebhookPayload(BaseModel):
    connection_id: int | None = None
    webhook_secret: str | None = None
    operation: str
    table: str | None = None
    summary: str
    rows_affected: int | None = None
    sql_preview: str | None = None
    author: str | None = None


class SchemaMonitorConfigUpdate(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    include_databases: list[str] | None = None
    exclude_databases: list[str] | None = None


class SchemaMonitorPingRequest(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None


class SchemaMonitorPingOut(BaseModel):
    ok: bool
    message: str
    latency_ms: float | None = None


class SchemaMonitorOut(BaseModel):
    subscription_id: int
    enabled: bool
    host: str | None = None
    port: int = 3306
    username: str | None = None
    password_set: bool = False
    connection_configured: bool = False
    include_databases: list[str] = Field(default_factory=list)
    exclude_databases: list[str] = Field(default_factory=list)
    interval_seconds: int
    last_scan_at: datetime | None = None
    last_error: str | None = None
    has_baseline: bool = False
    database_count: int = 0
    table_count: int = 0


class SchemaScanResultOut(BaseModel):
    subscription_id: int
    changes_detected: int
    logs_created: int
    has_baseline: bool
    message: str


class PublicConfigOut(BaseModel):
    webhook_base_url: str
    omnidb_base_url: str = ""
    sshwifty_base_url: str = ""


class OmnidbOpenOut(BaseModel):
    embed_url: str
    connection_name: str
    omnidb_connection_id: int | None = None


class SshwiftyOpenOut(BaseModel):
    embed_url: str
    connection_name: str


class RepoAccessSettingsOut(BaseModel):
    gitlab_base_url: str
    gitlab_token_set: bool
    gitlab_token_hint: str | None = None
    github_token_set: bool
    github_token_hint: str | None = None
    public_webhook_base_url: str
    updated_at: datetime | None = None


class RepoAccessSettingsUpdate(BaseModel):
    gitlab_base_url: str | None = None
    gitlab_token: str | None = None
    github_token: str | None = None
    public_webhook_base_url: str | None = None

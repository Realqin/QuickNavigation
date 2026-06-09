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
        allowed = {"project", "environment", "label"}
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
        allowed = {"project", "environment", "label"}
        if value not in allowed:
            raise ValueError(f"type 必须是 {', '.join(sorted(allowed))}")
        return value


class DictItemOut(BaseModel):
    id: int
    type: str
    name: str
    description: str | None
    sort_order: int
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
    url: str = Field(min_length=1, max_length=512)
    description: str | None = None
    projects: list[int] = Field(default_factory=list)
    environments: list[int] = Field(default_factory=list)
    type: int = Field(default=1)
    is_shared: bool = False
    sort_order: int = 0
    icon: str | None = None
    sub_links: list[SubLinkItem] = Field(default_factory=list)

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
    @field_validator("environments")
    @classmethod
    def validate_scope(cls, environments: list[int], info):
        data = info.data
        if not data.get("is_shared") and not environments:
            raise ValueError("非共用连接至少选择一个环境")
        return environments

    @field_validator("projects")
    @classmethod
    def validate_projects(cls, projects: list[int], info):
        data = info.data
        if not data.get("is_shared") and not projects:
            raise ValueError("非共用连接至少选择一个项目")
        return projects


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    url: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    projects: list[int] | None = None
    environments: list[int] | None = None
    type: int | None = None
    is_shared: bool | None = None
    sort_order: int | None = None
    icon: str | None = None
    sub_links: list[SubLinkItem] | None = None

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
    is_reachable: bool | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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


class HomeResponse(BaseModel):
    shared: list[ConnectionOut]
    scoped: list[ConnectionOut]
    projects: list[DictItemOut]
    environments: list[DictItemOut]
    labels: list[DictItemOut]


class SubscriptionBase(BaseModel):
    enabled: bool = True
    github_repo: str | None = None
    github_events: list[str] | None = None
    db_filter: dict[str, Any] | None = None
    notify_homepage: bool = True


class SubscriptionCreate(SubscriptionBase):
    connection_id: int


class SubscriptionUpdate(BaseModel):
    enabled: bool | None = None
    github_repo: str | None = None
    github_events: list[str] | None = None
    db_filter: dict[str, Any] | None = None
    notify_homepage: bool | None = None


class SubscriptionOut(SubscriptionBase):
    id: int
    connection_id: int
    webhook_secret: str
    webhook_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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

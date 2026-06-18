from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.llm_client import fetch_openai_compatible_models, test_openai_compatible_connection
from app.models import LlmConfig


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _serialize(config: LlmConfig) -> dict:
    return {
        "id": config.id,
        "name": config.name,
        "api_url": config.api_url,
        "api_key": "",
        "has_api_key": bool(config.api_key),
        "model_name": config.model_name,
        "context_limit": config.context_limit,
        "vision_enabled": config.vision_enabled,
        "stream_enabled": config.stream_enabled,
        "enabled": config.enabled,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


def _deactivate_other_configs(db: Session, active_id: str) -> None:
    rows = db.query(LlmConfig).filter(LlmConfig.id != active_id, LlmConfig.enabled.is_(True)).all()
    now = datetime.utcnow()
    for row in rows:
        row.enabled = False
        row.updated_at = now


def list_llm_configs(db: Session) -> list[dict]:
    rows = db.query(LlmConfig).order_by(LlmConfig.created_at.asc()).all()
    return [_serialize(row) for row in rows]


def create_llm_config(db: Session, payload: dict) -> dict:
    now = datetime.utcnow()
    config = LlmConfig(
        id=_new_id(),
        name=payload["name"],
        api_url=payload["api_url"],
        api_key=payload["api_key"],
        model_name=payload["model_name"],
        context_limit=payload.get("context_limit", 128000),
        vision_enabled=payload.get("vision_enabled", False),
        stream_enabled=payload.get("stream_enabled", True),
        enabled=payload.get("enabled", False),
        created_at=now,
        updated_at=now,
    )
    db.add(config)
    if config.enabled:
        _deactivate_other_configs(db, config.id)
    db.commit()
    db.refresh(config)
    return _serialize(config)


def update_llm_config(db: Session, config_id: str, payload: dict) -> dict:
    config = db.query(LlmConfig).filter(LlmConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")

    config.name = payload["name"]
    config.api_url = payload["api_url"]
    config.model_name = payload["model_name"]
    config.context_limit = payload.get("context_limit", 128000)
    config.vision_enabled = payload.get("vision_enabled", False)
    config.stream_enabled = payload.get("stream_enabled", True)
    config.enabled = payload.get("enabled", False)
    config.updated_at = datetime.utcnow()
    if payload.get("api_key"):
        config.api_key = payload["api_key"]
    if config.enabled:
        _deactivate_other_configs(db, config.id)
    db.commit()
    db.refresh(config)
    return _serialize(config)


def toggle_llm_config(db: Session, config_id: str, enabled: bool) -> dict:
    config = db.query(LlmConfig).filter(LlmConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    config.enabled = enabled
    config.updated_at = datetime.utcnow()
    if enabled:
        _deactivate_other_configs(db, config.id)
    db.commit()
    db.refresh(config)
    return _serialize(config)


def delete_llm_config(db: Session, config_id: str) -> None:
    config = db.query(LlmConfig).filter(LlmConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    db.delete(config)
    db.commit()


def get_llm_config(db: Session, config_id: str) -> LlmConfig:
    config = db.query(LlmConfig).filter(LlmConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    return config


def resolve_api_key(db: Session, *, api_key: str, config_id: str | None) -> str:
    key = (api_key or "").strip()
    if key:
        return key
    if not config_id:
        return ""
    config = db.query(LlmConfig).filter(LlmConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    return config.api_key or ""


async def test_llm_connection(db: Session, payload: dict) -> dict:
    api_key = resolve_api_key(db, api_key=payload.get("api_key", ""), config_id=payload.get("config_id"))
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空，请填写或先保存配置后再测试")
    context_limit = 128000
    config_id = payload.get("config_id")
    if config_id:
        config = db.query(LlmConfig).filter(LlmConfig.id == config_id).first()
        if config:
            context_limit = config.context_limit
    return await test_openai_compatible_connection(
        api_url=payload["api_url"],
        api_key=api_key,
        model_name=payload["model_name"],
        context_limit=context_limit,
    )


async def fetch_llm_models(db: Session, payload: dict) -> dict:
    api_key = resolve_api_key(db, api_key=payload.get("api_key", ""), config_id=payload.get("config_id"))
    models = await fetch_openai_compatible_models(
        api_url=payload["api_url"],
        api_key=api_key,
    )
    return {"items": models}


def get_active_llm_config(db: Session) -> LlmConfig:
    config = db.query(LlmConfig).filter(LlmConfig.enabled.is_(True)).first()
    if not config:
        raise HTTPException(status_code=400, detail="未找到已激活的 LLM 配置")
    if not config.api_url or not config.api_key or not config.model_name:
        raise HTTPException(status_code=400, detail="已激活的 LLM 配置不完整")
    return config


def seed_llm_configs(db: Session) -> None:
    if db.query(LlmConfig).count() > 0:
        return
    now = datetime.utcnow()
    seeds = [
        {
            "name": "qwen",
            "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "",
            "model_name": "qwen3.5-flash",
            "enabled": False,
        },
        {
            "name": "glm",
            "api_url": "https://open.bigmodel.cn/api/paas/v4",
            "api_key": "",
            "model_name": "glm-4.5-air",
            "enabled": False,
        },
    ]
    for item in seeds:
        db.add(
            LlmConfig(
                id=_new_id(),
                name=item["name"],
                api_url=item["api_url"],
                api_key=item["api_key"],
                model_name=item["model_name"],
                context_limit=128000,
                vision_enabled=False,
                stream_enabled=True,
                enabled=item["enabled"],
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Connection, DictItem, Subscription
from app.schemas import (
    ActivityLogOut,
    BatchDeleteRequest,
    ConnectionCreate,
    ConnectionOut,
    ConnectionUpdate,
    DictItemCreate,
    DictItemOut,
    DictItemUpdate,
    HomeResponse,
    ReorderRequest,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)
from app.services import (
    create_connection,
    create_dict_item,
    create_subscription,
    batch_delete_connections,
    delete_connection,
    delete_dict_item,
    get_home_data,
    list_activity_logs,
    list_connections,
    list_dict_items,
    reorder_connections,
    reorder_dict_items,
    update_connection,
    update_dict_item,
    update_subscription,
)

from app.ping_scheduler import ping_connection_record

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/dict", response_model=list[DictItemOut])
def get_dict_items(
    type: str | None = Query(None, alias="type"),
    db: Session = Depends(get_db),
):
    items = list_dict_items(db, dict_type=type)
    return [DictItemOut.from_orm_item(item) for item in items]


@router.post("/dict", response_model=DictItemOut, status_code=201)
def post_dict_item(data: DictItemCreate, db: Session = Depends(get_db)):
    item = create_dict_item(db, data)
    return DictItemOut.from_orm_item(item)


@router.patch("/dict/reorder")
def patch_dict_reorder(data: ReorderRequest, db: Session = Depends(get_db)):
    reorder_dict_items(db, [item.model_dump() for item in data.items])
    return {"ok": True, "scope": data.scope}


@router.patch("/dict/{item_id}", response_model=DictItemOut)
def patch_dict_item(item_id: int, data: DictItemUpdate, db: Session = Depends(get_db)):
    item = db.query(DictItem).filter(DictItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Dict item not found")
    item = update_dict_item(db, item, data)
    return DictItemOut.from_orm_item(item)


@router.delete("/dict/{item_id}", status_code=204)
def remove_dict_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(DictItem).filter(DictItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Dict item not found")
    delete_dict_item(db, item)


@router.get("/connections", response_model=list[ConnectionOut])
def get_connections(
    name: str | None = Query(None),
    project: int | None = Query(None),
    environment: int | None = Query(None),
    is_shared: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    return list_connections(
        db,
        name=name,
        project=project,
        environment=environment,
        is_shared=is_shared,
    )


@router.get("/connections/home", response_model=HomeResponse)
def get_home_connections(
    project: int = Query(...),
    environment: int = Query(...),
    db: Session = Depends(get_db),
):
    data = get_home_data(db, project, environment)
    return HomeResponse(
        shared=data["shared"],
        scoped=data["scoped"],
        projects=[DictItemOut.from_orm_item(item) for item in data["projects"]],
        environments=[DictItemOut.from_orm_item(item) for item in data["environments"]],
        labels=[DictItemOut.from_orm_item(item) for item in data["labels"]],
    )


@router.post("/connections", response_model=ConnectionOut, status_code=201)
def post_connection(data: ConnectionCreate, db: Session = Depends(get_db)):
    return create_connection(db, data)


@router.patch("/connections/reorder")
def patch_reorder(data: ReorderRequest, db: Session = Depends(get_db)):
    reorder_connections(db, [item.model_dump() for item in data.items])
    return {"ok": True, "scope": data.scope}


@router.post("/connections/batch-delete")
def post_batch_delete_connections(data: BatchDeleteRequest, db: Session = Depends(get_db)):
    deleted = batch_delete_connections(db, data.ids)
    return {"ok": True, "deleted": deleted}


@router.post("/connections/{connection_id}/ping", response_model=ConnectionOut)
async def post_connection_ping(
    connection_id: int,
    sub_index: int | None = Query(None, ge=0),
):
    connection = await ping_connection_record(connection_id, sub_index=sub_index)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection or sub-link not found")
    return connection


@router.get("/connections/{connection_id}", response_model=ConnectionOut)
def get_connection(connection_id: int, db: Session = Depends(get_db)):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.patch("/connections/{connection_id}", response_model=ConnectionOut)
def patch_connection(
    connection_id: int, data: ConnectionUpdate, db: Session = Depends(get_db)
):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return update_connection(db, conn, data)


@router.delete("/connections/{connection_id}", status_code=204)
def remove_connection(connection_id: int, db: Session = Depends(get_db)):
    conn = db.query(Connection).filter(Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    delete_connection(db, conn)


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def get_subscriptions(db: Session = Depends(get_db)):
    subs = db.query(Subscription).all()
    result = []
    for sub in subs:
        out = SubscriptionOut.model_validate(sub)
        out.webhook_url = f"/webhooks/database?secret={sub.webhook_secret}"
        result.append(out)
    return result


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
def post_subscription(data: SubscriptionCreate, db: Session = Depends(get_db)):
    conn = db.query(Connection).filter(Connection.id == data.connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if conn.subscription:
        raise HTTPException(status_code=400, detail="Subscription already exists")
    sub = create_subscription(db, data)
    out = SubscriptionOut.model_validate(sub)
    out.webhook_url = f"/webhooks/database?secret={sub.webhook_secret}"
    return out


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionOut)
def patch_subscription(
    subscription_id: int, data: SubscriptionUpdate, db: Session = Depends(get_db)
):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub = update_subscription(db, sub, data)
    out = SubscriptionOut.model_validate(sub)
    out.webhook_url = f"/webhooks/database?secret={sub.webhook_secret}"
    return out


@router.get("/logs", response_model=list[ActivityLogOut])
def get_logs(
    project: int | None = Query(None),
    environment: int | None = Query(None),
    source_type: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    return list_activity_logs(
        db, project=project, environment=environment, source_type=source_type, limit=limit
    )


@router.patch("/logs/{log_id}/read", response_model=ActivityLogOut)
def mark_log_read(log_id: int, db: Session = Depends(get_db)):
    from app.models import ActivityLog

    log = db.query(ActivityLog).filter(ActivityLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    log.is_read = True
    db.commit()
    db.refresh(log)
    return log

"""认证、用户管理与操作日志 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, require_admin, verify_password
from app.database import get_db
from app.menu_permissions import MENU_PERMISSION_TREE, user_has_menu
from app.models import User
from app.operation_log_service import (
    ACTION_LABELS,
    list_operation_logs,
    record_operation,
    record_page_open,
)
from app.schemas import (
    AuthLoginIn,
    AuthLoginOut,
    AuthMeOut,
    MenuPermissionNodeOut,
    OperationLogListOut,
    OperationLogOut,
    OperationLogReportIn,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.user_service import create_user, delete_user, get_user, list_users, update_user

router = APIRouter(prefix="/api", tags=["auth-users"])


def _user_out(user: User, *, include_password: bool = False) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        password=user.password_plain or "" if include_password else "",
        menu_permissions=user.menu_permissions or [],
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/auth/login", response_model=AuthLoginOut)
def login(payload: AuthLoginIn, request: Request, db: Session = Depends(get_db)):
    username = payload.username.strip()
    user = db.query(User).filter(User.username == username, User.is_active.is_(True)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token = create_access_token(user.id, user.username)
    record_operation(
        db,
        user=user,
        action="login",
        content="用户登录了",
        ip_address=request.client.host if request.client else None,
    )
    return AuthLoginOut(
        access_token=token,
        token_type="bearer",
        user=_user_out(user),
    )


@router.post("/auth/logout")
def logout(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record_operation(
        db,
        user=user,
        action="logout",
        content="退出登录了",
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True}


@router.get("/auth/me", response_model=AuthMeOut)
def auth_me(user: User = Depends(get_current_user)):
    return AuthMeOut(user=_user_out(user))


@router.get("/menu-permissions", response_model=list[MenuPermissionNodeOut])
def get_menu_permissions(_: User = Depends(get_current_user)):
    return [MenuPermissionNodeOut.model_validate(node) for node in MENU_PERMISSION_TREE]


@router.get("/users", response_model=list[UserOut])
def get_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_user_out(user, include_password=True) for user in list_users(db)]


@router.post("/users", response_model=UserOut)
def post_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    user = create_user(
        db,
        username=payload.username,
        nickname=payload.nickname,
        password=payload.password,
        menu_permissions=payload.menu_permissions,
        is_admin=payload.is_admin,
        is_active=payload.is_active,
    )
    record_operation(
        db,
        user=current,
        action="create",
        content=f"新增用户 {user.nickname}（{user.username}）",
        resource_type="用户",
        resource_id=str(user.id),
        ip_address=request.client.host if request.client else None,
    )
    return _user_out(user, include_password=True)


@router.put("/users/{user_id}", response_model=UserOut)
def put_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    fields = payload.model_dump(exclude_unset=True)
    user = update_user(db, user, **fields)
    record_operation(
        db,
        user=current,
        action="update",
        content=f"编辑用户 {user.nickname}（{user.username}）",
        resource_type="用户",
        resource_id=str(user.id),
        ip_address=request.client.host if request.client else None,
    )
    return _user_out(user, include_password=True)


@router.delete("/users/{user_id}")
def remove_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    nickname = user.nickname
    username = user.username
    delete_user(db, user, current_user=current)
    record_operation(
        db,
        user=current,
        action="delete",
        content=f"删除用户 {nickname}（{username}）",
        resource_type="用户",
        resource_id=str(user_id),
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True}


@router.get("/operation-logs", response_model=OperationLogListOut)
def get_operation_logs(
    keyword: str | None = Query(default=None),
    action: str | None = Query(default=None),
    username: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user_has_menu(user, "operationLogs"):
        raise HTTPException(status_code=403, detail="无操作日志查看权限")
    rows, total = list_operation_logs(
        db,
        keyword=keyword,
        action=action,
        username=username,
        limit=limit,
        offset=offset,
    )
    return OperationLogListOut(
        items=[
            OperationLogOut(
                id=row.id,
                user_id=row.user_id,
                username=row.username,
                action=row.action,
                action_label=ACTION_LABELS.get(row.action, row.action),
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                content=row.content,
                ip_address=row.ip_address,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
    )


@router.post("/operation-logs/report")
def report_operation_log(
    payload: OperationLogReportIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.action == "open":
        record_page_open(
            db,
            user=user,
            menu_key=payload.menu_key or "",
            ip_address=request.client.host if request.client else None,
        )
        return {"ok": True}
    record_operation(
        db,
        user=user,
        action=payload.action,
        content=payload.content,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True}

"""用户管理 CRUD。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.menu_permissions import all_menu_keys, user_has_menu
from app.models import User


def list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.id.asc()).all()


def get_user(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def _normalize_permissions(menu_permissions: list[str] | None, *, is_admin: bool) -> list[str]:
    if is_admin:
        return all_menu_keys()
    keys = [key for key in (menu_permissions or []) if key in all_menu_keys()]
    return keys


def create_user(
    db: Session,
    *,
    username: str,
    nickname: str,
    password: str,
    menu_permissions: list[str] | None,
    is_admin: bool = False,
    is_active: bool = True,
) -> User:
    username = username.strip()
    nickname = nickname.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户 ID 不能为空")
    if not nickname:
        raise HTTPException(status_code=400, detail="昵称不能为空")
    if not password.strip():
        raise HTTPException(status_code=400, detail="密码不能为空")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户 ID 已存在")
    user = User(
        username=username,
        nickname=nickname,
        password_hash=hash_password(password),
        password_plain=password.strip(),
        menu_permissions=_normalize_permissions(menu_permissions, is_admin=is_admin),
        is_admin=is_admin,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, **updates) -> User:
    nickname = updates.get("nickname")
    password = updates.get("password")
    menu_permissions = updates.get("menu_permissions")
    is_admin = updates.get("is_admin")
    is_active = updates.get("is_active")
    if nickname is not None:
        text = nickname.strip()
        if not text:
            raise HTTPException(status_code=400, detail="昵称不能为空")
        user.nickname = text
    if password is not None and password.strip():
        plain = password.strip()
        user.password_hash = hash_password(plain)
        user.password_plain = plain
    if is_admin is not None:
        user.is_admin = is_admin
    if is_active is not None:
        user.is_active = is_active
    if menu_permissions is not None or is_admin is not None:
        user.menu_permissions = _normalize_permissions(
            menu_permissions if menu_permissions is not None else user.menu_permissions,
            is_admin=user.is_admin,
        )
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User, *, current_user: User) -> None:
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")
    if user.is_admin and db.query(User).filter(User.is_admin.is_(True)).count() <= 1:
        raise HTTPException(status_code=400, detail="至少保留一名管理员")
    db.delete(user)
    db.commit()


def ensure_menu_permission(user: User, menu_key: str) -> None:
    if not user_has_menu(user, menu_key):
        raise HTTPException(status_code=403, detail="无菜单访问权限")

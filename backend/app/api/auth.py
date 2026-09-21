"""登录身份 API (演示环境使用令牌做轻量身份切换)."""
from flask import Blueprint

from ..models import User
from ..services import access_service

bp = Blueprint("auth", __name__)


@bp.get("/me")
def me():
    """当前登录人及其生效中的可录入范围。"""
    user = access_service.current_user()
    if user is None:
        return {"user": None}
    return {"user": user.to_dict(include_scope=True)}


@bp.get("/users")
def users():
    """人员清单, 供顶栏切换登录人 / 录入表单选择代录对象。"""
    only_active = access_service.current_user() is None
    query = User.query
    if only_active:
        query = query.filter_by(is_active=True)
    items = [
        {
            "id": row.id,
            "username": row.username,
            "name": row.name,
            "is_active": bool(row.is_active),
            "is_admin": bool(row.is_admin),
            "position_id": row.position_id,
            "position_name": row.position.name if row.position else None,
            "token": row.token,
        }
        for row in query.order_by(User.id.asc()).all()
    ]
    return {"items": items}

"""岗位与录入权限管理 API (仅管理员)。

范围调整通过“登记新生效版本”完成 (带生效时间), 从不就地改写旧口径,
历史数据归属按登记当时的口径版本保留。
"""
from flask import Blueprint

from ..services import access_service, admin_service
from .helpers import json_payload

bp = Blueprint("admin", __name__)


@bp.before_request
def _require_admin():
    access_service.require_admin()


# ---------------- 岗位 ----------------

@bp.get("/positions")
def list_positions():
    return {"items": [p.to_dict(include_scopes=True) for p in admin_service.list_positions()]}


@bp.post("/positions")
def create_position():
    data = json_payload()
    position = admin_service.create_position(data)
    return position.to_dict(include_scopes=True), 201


@bp.put("/positions/<int:position_id>")
def update_position(position_id):
    position = admin_service.get_position(position_id)
    position = admin_service.update_position(position, json_payload())
    return position.to_dict(include_scopes=True)


# ---------------- 口径版本 ----------------

@bp.get("/positions/<int:position_id>/scopes")
def list_scopes(position_id):
    return {"items": [s.to_dict() for s in admin_service.list_scopes(position_id)]}


@bp.post("/positions/<int:position_id>/scopes")
def create_scope(position_id):
    """为岗位登记一版新的可录入范围, 自生效时间起仅影响此后的录入。"""
    scope = admin_service.create_scope(position_id, json_payload())
    return scope.to_dict(), 201


# ---------------- 人员 ----------------

@bp.get("/users")
def list_users():
    return {"items": [u.to_dict(include_scope=True) for u in admin_service.list_users()]}


@bp.post("/users")
def create_user():
    user = admin_service.create_user(json_payload())
    payload = user.to_dict(include_scope=True)
    payload["token"] = user.token
    return payload, 201


@bp.put("/users/<int:user_id>")
def update_user(user_id):
    from ..extensions import db

    user = db.session.get(admin_service.User, user_id)
    if user is None:
        from ..errors import NotFoundError

        raise NotFoundError("人员不存在: id=%s" % user_id)
    user = admin_service.update_user(user, json_payload())
    return user.to_dict(include_scope=True)

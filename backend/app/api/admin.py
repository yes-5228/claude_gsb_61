"""岗位 / 用户 / 录入范围管理 API (仅管理员)。"""
from functools import wraps

from flask import Blueprint

from ..services import auth_service, identity_service
from .helpers import json_payload

bp = Blueprint("admin", __name__)


def admin_required(view):
    @wraps(view)
    def _wrapped(*args, **kwargs):
        user = auth_service.current_user()
        if not (user.position and user.position.is_admin):
            from ..errors import PermissionDeniedError as Denied

            raise Denied("仅系统管理员可进行岗位与人员管理", code="ADMIN_ONLY")
        return view(*args, **kwargs)

    return _wrapped


# --------------------------------------------------------------- positions
@bp.get("/positions")
@admin_required
def list_positions():
    return {"items": [item.to_dict(include_scope=True) for item in identity_service.list_positions()]}


@bp.post("/positions")
@admin_required
def create_position():
    return identity_service.create_position(json_payload()).to_dict(include_scope=True), 201


@bp.put("/positions/<int:position_id>")
@admin_required
def update_position(position_id):
    return identity_service.update_position(position_id, json_payload()).to_dict(include_scope=True)


@bp.post("/positions/<int:position_id>/scope-versions")
@admin_required
def add_scope_version(position_id):
    """调整岗位可录入范围 (带生效时间, 只影响此后的录入)。"""
    version = identity_service.add_scope_version(position_id, json_payload())
    return version.to_dict(), 201


# ------------------------------------------------------------------- users
@bp.get("/users")
@admin_required
def list_users():
    return {"items": [item.to_dict(include_scope=True) for item in identity_service.list_users()]}


@bp.post("/users")
@admin_required
def create_user():
    return identity_service.create_user(json_payload()).to_dict(include_scope=True), 201


@bp.put("/users/<int:user_id>")
@admin_required
def update_user(user_id):
    return identity_service.update_user(user_id, json_payload()).to_dict(include_scope=True)

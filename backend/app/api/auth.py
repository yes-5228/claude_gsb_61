"""登录认证 API。"""
from flask import Blueprint

from ..services import auth_service
from .helpers import json_payload

bp = Blueprint("auth", __name__)


@bp.post("/login")
def login():
    data = json_payload()
    user, token = auth_service.authenticate(data.get("username"), data.get("password"))
    return {"token": token, "user": user.to_dict(include_scope=True)}, 200


@bp.get("/me")
def me():
    """获取当前登录人与其当前生效的可录入范围。"""
    user = auth_service.current_user()
    return user.to_dict(include_scope=True)

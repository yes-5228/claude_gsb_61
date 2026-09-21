"""岗位 / 用户 / 岗位范围版本的管理业务逻辑。"""
from datetime import datetime

from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Position, PositionScopeVersion, User, hash_password
from ..utils.validation import parse_datetime


# ---------------------------------------------------------------- positions
def list_positions():
    return Position.query.order_by(Position.id.asc()).all()


def get_position(position_id):
    position = db.session.get(Position, position_id)
    if position is None:
        raise NotFoundError("岗位不存在: id=%s" % position_id)
    return position


def create_position(payload):
    code = (payload.get("code") or "").strip()
    name = (payload.get("name") or "").strip()
    if not code:
        raise ValidationError("岗位编码不能为空", fields={"code": "required"})
    if not name:
        raise ValidationError("岗位名称不能为空", fields={"name": "required"})
    if Position.query.filter_by(code=code).first():
        raise ConflictError("岗位编码已存在: %s" % code)
    position = Position(
        code=code,
        name=name,
        can_proxy=bool(payload.get("can_proxy", False)),
        is_admin=bool(payload.get("is_admin", False)),
        remark=(payload.get("remark") or None),
    )
    db.session.add(position)
    db.session.flush()

    scope = payload.get("scope")
    if not position.is_admin and scope is not None:
        _add_scope_version(position, scope, effective_from=datetime.now())
    db.session.commit()
    return position


def update_position(position_id, payload):
    position = get_position(position_id)
    if "name" in payload and str(payload["name"]).strip():
        position.name = str(payload["name"]).strip()
    if "can_proxy" in payload:
        position.can_proxy = bool(payload["can_proxy"])
    if "remark" in payload:
        position.remark = payload["remark"] or None
    if "active" in payload:
        position.active = bool(payload["active"])
    db.session.commit()
    return position


def add_scope_version(position_id, payload):
    """新增一版可录入范围, 带生效时间; 只影响该时间之后的录入。"""
    position = get_position(position_id)
    if position.is_admin:
        raise ValidationError("管理员岗位默认全量可录, 无需配置范围",
                              fields={"position_id": "admin_unrestricted"})
    version = _add_scope_version(
        position,
        payload,
        effective_from=parse_datetime(payload.get("effective_from"), "生效时间"),
    )
    db.session.commit()
    return version


def _add_scope_version(position, scope, effective_from):
    if not isinstance(scope, dict):
        raise ValidationError("范围配置 scope 必须为对象", fields={"scope": "invalid"})
    all_stations = bool(scope.get("all_stations", True))
    all_pollutants = bool(scope.get("all_pollutants", True))
    station_codes = scope.get("station_codes") or []
    pollutant_codes = scope.get("pollutant_codes") or []
    if not isinstance(station_codes, list) or not isinstance(pollutant_codes, list):
        raise ValidationError("点位/因子范围必须为数组", fields={"scope": "invalid"})
    if not all_stations and not station_codes:
        raise ValidationError("限制点位范围时至少选择一个监测点",
                              fields={"station_codes": "empty"})
    if not all_pollutants and not pollutant_codes:
        raise ValidationError("限制因子范围时至少选择一个因子",
                              fields={"pollutant_codes": "empty"})
    version = PositionScopeVersion(
        position_id=position.id,
        effective_from=effective_from,
        all_stations=all_stations,
        all_pollutants=all_pollutants,
        remark=(scope.get("remark") or None),
    )
    version.station_codes = station_codes
    version.pollutant_codes = pollutant_codes
    db.session.add(version)
    db.session.flush()
    return version


# -------------------------------------------------------------------- users
def list_users():
    return User.query.order_by(User.id.asc()).all()


def get_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在: id=%s" % user_id)
    return user


def _get_position_ref(position_id):
    position = db.session.get(Position, int(position_id)) if position_id else None
    if position is None:
        raise ValidationError("所属岗位不存在", fields={"position_id": "not_found"})
    return position


def create_user(payload):
    username = (payload.get("username") or "").strip()
    display_name = (payload.get("display_name") or "").strip()
    password = payload.get("password") or ""
    if not username:
        raise ValidationError("登录账号不能为空", fields={"username": "required"})
    if not display_name:
        raise ValidationError("姓名不能为空", fields={"display_name": "required"})
    if len(password) < 6:
        raise ValidationError("登录密码至少 6 位", fields={"password": "too_short"})
    if User.query.filter_by(username=username).first():
        raise ConflictError("登录账号已存在: %s" % username)
    position = _get_position_ref(payload.get("position_id"))
    user = User(
        username=username,
        display_name=display_name,
        position=position,
        active=bool(payload.get("active", True)),
        remark=(payload.get("remark") or None),
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def update_user(user_id, payload):
    """调岗 / 停用即时生效 (录入授权每次实时查库)。"""
    user = get_user(user_id)
    if "display_name" in payload and str(payload["display_name"]).strip():
        user.display_name = str(payload["display_name"]).strip()
    if "position_id" in payload and payload["position_id"]:
        user.position = _get_position_ref(payload["position_id"])
    if "active" in payload:
        user.active = bool(payload["active"])
    if "remark" in payload:
        user.remark = payload["remark"] or None
    if payload.get("password"):
        if len(str(payload["password"])) < 6:
            raise ValidationError("登录密码至少 6 位", fields={"password": "too_short"})
        user.set_password(str(payload["password"]))
    db.session.commit()
    return user

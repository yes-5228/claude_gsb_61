"""岗位、口径版本与人员的管理业务逻辑."""
from datetime import datetime

from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Position, PositionScope, ScopePollutant, Station, User
from ..domain.standards import POLLUTANT_CODES


# ---------------- 岗位 ----------------

def list_positions():
    return Position.query.order_by(Position.id.asc()).all()


def get_position(position_id):
    position = db.session.get(Position, position_id)
    if position is None:
        raise NotFoundError("岗位不存在: id=%s" % position_id)
    return position


def create_position(data):
    code = _required_text(data, "code", "岗位编码", 32)
    name = _required_text(data, "name", "岗位名称", 64)
    if Position.query.filter_by(code=code).first():
        raise ConflictError("岗位编码已存在: %s" % code)
    position = Position(
        code=code, name=name,
        description=(data.get("description") or None),
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(position)
    db.session.commit()
    return position


def update_position(position, data):
    if "name" in data:
        name = _required_text(data, "name", "岗位名称", 64)
        position.name = name
    if "description" in data:
        position.description = (data.get("description") or None)
    if "is_active" in data:
        position.is_active = bool(data["is_active"])
    db.session.commit()
    return position


# ---------------- 口径版本 (范围调整带生效时间) ----------------

def list_scopes(position_id):
    get_position(position_id)
    return (
        PositionScope.query.filter_by(position_id=position_id)
        .order_by(PositionScope.effective_from.desc())
        .all()
    )


def create_scope(position_id, data):
    """登记一版新生效的录入口径。

    范围调整不覆盖旧版本: 新版本自 ``effective_from`` 起生效, 仅影响此后的录入;
    同一岗位不允许两版口径在同一时刻生效。
    """
    position = get_position(position_id)
    effective_from = _parse_effective_from(data.get("effective_from"))

    if PositionScope.query.filter_by(position_id=position.id,
                                    effective_from=effective_from).first():
        raise ConflictError(
            "岗位「%s」在 %s 已存在一版口径, 生效时间不能重复"
            % (position.name, effective_from.strftime("%Y-%m-%d %H:%M"))
        )

    all_stations = bool(data.get("all_stations", False))
    all_pollutants = bool(data.get("all_pollutants", False))
    station_ids = _normalise_station_ids(data.get("station_ids"), all_stations)
    pollutants = _normalise_pollutants(data.get("pollutants"), all_pollutants)

    scope = PositionScope(
        position_id=position.id,
        effective_from=effective_from,
        all_stations=all_stations,
        all_pollutants=all_pollutants,
        remark=(data.get("remark") or None),
    )
    db.session.add(scope)
    db.session.flush()
    if not all_stations:
        stations = Station.query.filter(Station.id.in_(station_ids)).all()
        scope.stations = stations
    if not all_pollutants:
        scope.pollutant_codes = [ScopePollutant(pollutant=code) for code in pollutants]

    db.session.commit()
    return scope


def _parse_effective_from(raw):
    if raw in (None, ""):
        return datetime.now()
    if isinstance(raw, datetime):
        return raw
    from ..utils.validation import parse_datetime

    return parse_datetime(raw, "生效时间")


def _normalise_station_ids(raw, all_stations):
    if all_stations:
        return []
    if not isinstance(raw, list) or not raw:
        raise ValidationError(
            "未勾选“全部监测点”时, 必须明确选择可录入的监测点范围",
            fields={"station_ids": "empty"},
        )
    try:
        ids = [int(item) for item in raw]
    except (TypeError, ValueError):
        raise ValidationError("监测点编号不合法", fields={"station_ids": "invalid"})
    found = {row.id for row in Station.query.filter(Station.id.in_(ids)).all()}
    missing = [item for item in ids if item not in found]
    if missing:
        raise ValidationError(
            "监测点不存在: %s" % ", ".join(str(item) for item in missing),
            fields={"station_ids": "not_found"},
        )
    return ids


def _normalise_pollutants(raw, all_pollutants):
    if all_pollutants:
        return []
    if not isinstance(raw, list) or not raw:
        raise ValidationError(
            "未勾选“全部因子”时, 必须明确选择可录入的监测因子范围",
            fields={"pollutants": "empty"},
        )
    codes = [str(item).strip().upper() for item in raw]
    invalid = [code for code in codes if code not in POLLUTANT_CODES]
    if invalid:
        raise ValidationError(
            "未知监测因子: %s" % ", ".join(invalid), fields={"pollutants": "unknown"}
        )
    return codes


def _required_text(data, field, label, max_length):
    value = str(data.get(field) or "").strip()
    if not value:
        raise ValidationError("%s不能为空" % label, fields={field: "required"})
    if len(value) > max_length:
        raise ValidationError("%s长度不能超过 %d" % (label, max_length), fields={field: "too_long"})
    return value


# ---------------- 人员 ----------------

def list_users():
    return User.query.order_by(User.id.asc()).all()


def create_user(data):
    username = _required_text(data, "username", "登录账号", 32)
    name = _required_text(data, "name", "姓名", 64)
    if User.query.filter_by(username=username).first():
        raise ConflictError("登录账号已存在: %s" % username)

    position_id = data.get("position_id")
    position = None
    if position_id not in (None, ""):
        position = get_position(int(position_id))

    user = User(
        username=username,
        name=name,
        token=User.generate_token(),
        is_active=bool(data.get("is_active", True)),
        is_admin=bool(data.get("is_admin", False)),
        position_id=position.id if position else None,
    )
    db.session.add(user)
    db.session.commit()
    return user


def update_user(user, data):
    """调岗 / 停用等变更直接落库, 下一次提交即按新状态鉴权 (无缓存)。"""
    if "name" in data:
        user.name = _required_text(data, "name", "姓名", 64)
    if "is_active" in data:
        user.is_active = bool(data["is_active"])
    if "is_admin" in data:
        user.is_admin = bool(data["is_admin"])
    if "position_id" in data:
        raw = data.get("position_id")
        if raw in (None, ""):
            user.position_id = None
        else:
            position = get_position(int(raw))
            user.position_id = position.id
    db.session.commit()
    return user


def rotate_token(user):
    user.token = User.generate_token()
    db.session.commit()
    return user

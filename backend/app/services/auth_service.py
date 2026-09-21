"""认证与"岗位可录入范围"授权。

所有越权判定都集中在服务层完成, API 层只负责取出当前登录人,
因此绕过页面直接 POST 接口同样会被拦截。
"""
from datetime import datetime

from flask import request

from ..errors import AuthenticationError, PermissionDeniedError, ValidationError
from ..extensions import db
from ..models import PositionScopeVersion, Station, User
from ..utils.tokens import make_token, read_token

TOKEN_TTL_SECONDS = 12 * 3600
HEADER_PREFIX = "Bearer "


# ---------------------------------------------------------------- login
def authenticate(username, password):
    user = User.query.filter_by(username=(username or "").strip()).first()
    if user is None or not user.check_password(password or ""):
        raise PermissionDeniedError("用户名或密码不正确", code="BAD_CREDENTIALS")
    if not user.active or not user.position or not user.position.active:
        raise PermissionDeniedError("账号或所属岗位已停用, 无法登录, 请联系管理员",
                                    code="ACCOUNT_DISABLED")
    user.last_login_at = datetime.now()
    db.session.commit()
    token = make_token({"uid": user.id, "ts": int(datetime.now().timestamp())})
    return user, token


# ----------------------------------------------------------- current user
def _token_from_request():
    header = request.headers.get("Authorization", "")
    if header.startswith(HEADER_PREFIX):
        return header[len(HEADER_PREFIX):].strip()
    return request.headers.get("X-Auth-Token", "").strip() or None


def current_user(required=True):
    """从请求令牌解析当前登录用户 (每次实时查库, 停用/调岗立即生效)。"""
    token = _token_from_request()
    payload = read_token(token) if token else None
    user = db.session.get(User, payload["uid"]) if payload and "uid" in payload else None
    if user is None or not user.active or not user.position or not user.position.active:
        if required:
            raise AuthenticationError()
        return None
    return user


# ------------------------------------------------------------- scope rule
def _describe_stations(scope):
    if scope.all_stations:
        return "全部监测点"
    codes = scope.station_codes
    if not codes:
        return "未开放任何监测点"
    stations = Station.query.filter(Station.code.in_(codes)).all()
    names = {s.code: s.name for s in stations}
    shown = "、".join("%s %s" % (code, names.get(code, "")) for code in codes[:5])
    if len(codes) > 5:
        shown += " 等 %d 个点位" % len(codes)
    return "仅 " + shown


def _describe_pollutants(scope, labels):
    if scope.all_pollutants:
        return "全部监测因子"
    codes = scope.pollutant_codes
    if not codes:
        return "未开放任何因子"
    return "仅 " + "、".join(labels.get(code, code) for code in codes)


def effective_scope(user, at=None):
    """用户在 ``at`` 时刻生效的范围版本; 管理员返回 None(全量)。"""
    if user.position.is_admin:
        return None
    return user.position.current_scope(at)


def assert_can_record(user, station, pollutant_codes, pollutant_labels=None, at=None):
    """按岗位当前生效范围校验点位 + 因子, 越权直接抛 403 并给出明确提示。

    返回用于快照的 (scope_version 或 None, scope_position_id)。
    """
    at = at or datetime.now()
    pollutant_labels = pollutant_labels or {}
    if user.position.is_admin:
        return None, user.position_id

    scope = user.position.current_scope(at)
    if scope is None:
        raise PermissionDeniedError(
            "提交被拦截: 您的岗位「%s」尚未配置任何可录入范围, 请联系管理员配置后再试。"
            % user.position.name,
            code="SCOPE_NOT_CONFIGURED",
        )

    problems = []
    station_ok = scope.all_stations or station.code in scope.station_codes
    if not station_ok:
        problems.append(
            "监测点「%s %s」不在可录入范围内" % (station.code, station.name)
        )

    denied = []
    if not scope.all_pollutants:
        allowed = set(scope.pollutant_codes)
        denied = [code for code in pollutant_codes if code not in allowed]
    if denied:
        problems.append(
            "因子 %s 不在可录入范围内"
            % "、".join("%s(%s)" % (pollutant_labels.get(code, code), code) for code in denied)
        )

    if problems:
        fields = {}
        if not station_ok:
            fields["station_id"] = "out_of_scope"
        for code in denied:
            fields[code] = "out_of_scope"
        raise PermissionDeniedError(
            "越权提交已被拦截: %s。您当前岗位「%s」的可录入范围为【%s】与【%s】; "
            "范围如需调整请联系管理员, 调整自设定的生效时间起仅影响此后的录入。"
            % (
                "；".join(problems),
                user.position.name,
                _describe_stations(scope),
                _describe_pollutants(scope, pollutant_labels),
            ),
            code="OUT_OF_SCOPE",
            fields=fields,
        )
    return scope, user.position_id


# ---------------------------------------------------------------- proxy
def resolve_proxy_target(operator, on_behalf_of_id):
    """解析代录对象; 无代录返回 operator 本人。

    - 只有岗位勾选了"允许代录"(或管理员)才能代录;
    - 被代录人必须是启用状态的账号, 录入人归属被代录人, 操作人记实际提交者。
    """
    if not on_behalf_of_id:
        return operator
    if not (operator.position.is_admin or operator.position.can_proxy):
        raise PermissionDeniedError(
            "代录被拦截: 您的岗位「%s」没有代录权限" % operator.position.name,
            code="PROXY_FORBIDDEN",
        )
    target = db.session.get(User, int(on_behalf_of_id))
    if target is None:
        raise ValidationError("代录对象不存在", fields={"on_behalf_of_id": "not_found"})
    if not target.active or not target.position or not target.position.active:
        raise ValidationError("被代录人已停用或其岗位已停用, 无法代为录入",
                              fields={"on_behalf_of_id": "inactive"})
    if target.id == operator.id:
        return operator
    return target

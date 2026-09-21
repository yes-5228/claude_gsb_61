"""登录身份解析与录入权限校验.

所有判断都实时查询数据库, 不做缓存: 账号被停用或调岗后, 下一次提交立即按新状态
收紧范围, 不存在“旧权限还能用一会儿”的窗口。绕过页面直接调用 API 也会经过
同一套校验。
"""
from flask import request

from ..errors import AuthenticationError, PermissionDeniedError
from ..models import PositionScope, User

OPERATOR_HEADER = "X-Operator-Token"


def current_user():
    """按请求头令牌解析当前登录人; 未携带/令牌无效时返回 None。"""
    token = request.headers.get(OPERATOR_HEADER, "").strip()
    if not token:
        return None
    return User.query.filter_by(token=token).first()


def current_user_id():
    user = current_user()
    return user.id if user else None


def require_user():
    """录入等写操作的登录门禁。"""
    user = current_user()
    if user is None:
        raise AuthenticationError(
            "未检测到登录身份, 请先在页面右上角选择登录人员后再提交录入"
        )
    if not user.is_active:
        raise PermissionDeniedError(
            "当前登录账号「%s」已被停用, 不能再录入数据; 请联系管理员" % user.name
        )
    return user


def require_admin():
    user = require_user()
    if not user.is_admin:
        raise PermissionDeniedError("仅系统管理员可以进行岗位与权限配置")
    return user


def _denied(user, message, **fields):
    raise PermissionDeniedError(message, fields=fields or None)


def effective_scope(user, at=None):
    """返回用户在 ``at`` 时刻实际生效的口径; 不可录入时返回 None。"""
    if user is None or not user.is_active:
        return None
    if user.position is None or not user.position.is_active:
        return None
    return user.position.current_scope(at=at)


def authorize_entry(user, station_id, pollutants, at=None, station_name=None,
                    pollutant_labels=None):
    """校验当前登录人是否可以向指定点位提交指定因子的录入。

    判定规则 (任一不通过即 403):
    1. 账号启用且所属岗位启用;
    2. 岗位在提交时刻存在已生效的口径版本;
    3. 监测点在口径允许范围内;
    4. 本次提交的每个因子都在口径允许范围内。
    """
    if user is None or not user.is_active:
        _denied(user, "登录账号不可用, 无法提交录入", user="inactive")

    if user.position is None:
        _denied(
            user,
            "账号「%s」尚未分配岗位, 没有任何监测点的录入权限, 请联系管理员配置" % user.name,
            position="missing",
        )
    if not user.position.is_active:
        _denied(
            user,
            "所属岗位「%s」已停用, 录入权限已收回, 不能继续提交" % user.position.name,
            position="inactive",
        )

    scope = user.position.current_scope(at=at)
    if scope is None:
        _denied(
            user,
            "岗位「%s」尚未配置已生效的录入范围 (没有在当前时间之前生效的口径), "
            "暂不能录入任何数据" % user.position.name,
            scope="missing",
        )

    # ---- 点位范围 ----
    if not scope.all_stations and station_id not in scope.station_ids():
        target = station_name or ("id=%s" % station_id)
        _denied(
            user,
            "越权提交被拦截: 您的岗位「%s」无权向监测点「%s」录入数据, "
            "该点位不在您当前的可录入点位范围内" % (user.position.name, target),
            station_id="out_of_scope",
        )

    # ---- 因子范围 ----
    allowed = set(scope.pollutants)
    if not scope.all_pollutants:
        labels = pollutant_labels or {}
        blocked = [code for code in pollutants if code not in allowed]
        if blocked:
            named = [
                "%s(%s)" % (labels.get(code, code), code) if labels.get(code) else code
                for code in blocked
            ]
            _denied(
                user,
                "越权提交被拦截: 您的岗位「%s」无权录入因子 %s, "
                "这些因子不在您当前的可录入因子范围内" % (user.position.name, "、".join(named)),
                pollutants="out_of_scope",
            )
    return scope


def scope_station_ids(scope):
    if scope is None:
        return []
    return scope.station_ids()


def scope_pollutants(scope):
    if scope is None:
        return []
    if scope.all_pollutants:
        from ..domain.standards import POLLUTANT_CODES

        return list(POLLUTANT_CODES)
    return scope.pollutants

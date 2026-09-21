from datetime import datetime

import pytest

from app import create_app
from app.extensions import db
from app.models import Position, PositionScope, ScopePollutant, Station, User
from app.services import station_service

ADMIN_TOKEN = "test-token-admin"


def _make_user(username, name, token, position=None, is_admin=False, is_active=True):
    user = User(
        username=username, name=name, token=token,
        is_active=is_active, is_admin=is_admin,
        position_id=position.id if position else None,
    )
    db.session.add(user)
    return user


@pytest.fixture
def auth_data(app):
    """岗位/口径/人员: 管理员(全域) + 受限录入员(仅 TEST-001 的 PM25/SO2)。"""
    admin_pos = Position(code="ADMIN", name="系统管理员", is_active=True)
    db.session.add(admin_pos)
    db.session.flush()
    admin_scope = PositionScope(
        position_id=admin_pos.id, effective_from=datetime(2000, 1, 1),
        all_stations=True, all_pollutants=True, remark="全域口径",
    )
    db.session.add(admin_scope)

    op_pos = Position(code="OP", name="一区录入员", is_active=True)
    db.session.add(op_pos)
    db.session.flush()

    other_pos = Position(code="OTHER", name="二区录入员", is_active=True)
    db.session.add(other_pos)
    db.session.flush()

    admin = _make_user("admin", "管理员", ADMIN_TOKEN, admin_pos, is_admin=True)
    return {
        "admin_pos": admin_pos,
        "admin_scope": admin_scope,
        "op_pos": op_pos,
        "other_pos": other_pos,
        "admin": admin,
    }


@pytest.fixture
def station(app):
    return station_service.create_station(
        {
            "code": "TEST-001",
            "name": "测试监测点",
            "area": "测试区",
            "address": "测试路 1 号",
            "station_type": "ambient",
            "status": "active",
            "longitude": 114.05,
            "latitude": 22.54,
            "installed_at": None,
            "remark": None,
        }
    )


@pytest.fixture
def second_station(app):
    return station_service.create_station(
        {
            "code": "TEST-002",
            "name": "工业园监测点",
            "area": "工业园区",
            "address": None,
            "station_type": "industrial",
            "status": "active",
            "longitude": None,
            "latitude": None,
            "installed_at": None,
            "remark": None,
        }
    )


@pytest.fixture
def scoped_operator(app, auth_data, station):
    """只能向 TEST-001 录入 PM25、SO2 的岗位与人员 (含另一同岗人员用于代录测试)。"""
    scope = PositionScope(
        position_id=auth_data["op_pos"].id, effective_from=datetime(2000, 1, 1),
        all_stations=False, all_pollutants=False, remark="单点位双因子",
    )
    db.session.add(scope)
    db.session.flush()
    scope.stations = [station]
    scope.pollutant_codes = [ScopePollutant(pollutant="PM25"), ScopePollutant(pollutant="SO2")]

    operator = _make_user("operator", "录入员甲", "test-token-operator", auth_data["op_pos"])
    colleague = _make_user("colleague", "录入员乙", "test-token-colleague", auth_data["op_pos"])
    db.session.commit()
    return {"user": operator, "colleague": colleague, "position": auth_data["op_pos"], "scope": scope}


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


class HeaderClient:
    """给每个请求自动带上登录令牌头的轻量包装 (旧版 Werkzeug Client 不支持构造器传头)。"""

    def __init__(self, app, token=None):
        self._client = app.test_client()
        self._token = token

    def _headers(self, headers):
        merged = dict(headers or {})
        if self._token:
            merged.setdefault("X-Operator-Token", self._token)
        return merged

    def get(self, path, headers=None, **kwargs):
        return self._client.get(path, headers=self._headers(headers), **kwargs)

    def post(self, path, headers=None, **kwargs):
        return self._client.post(path, headers=self._headers(headers), **kwargs)

    def put(self, path, headers=None, **kwargs):
        return self._client.put(path, headers=self._headers(headers), **kwargs)

    def patch(self, path, headers=None, **kwargs):
        return self._client.patch(path, headers=self._headers(headers), **kwargs)

    def delete(self, path, headers=None, **kwargs):
        return self._client.delete(path, headers=self._headers(headers), **kwargs)


@pytest.fixture
def client(app, auth_data):
    # 默认以全域管理员身份访问; 越权用例使用 client_as(...) 切换身份
    db.session.commit()
    return HeaderClient(app, ADMIN_TOKEN)


@pytest.fixture
def anon_client(app):
    """不带登录令牌的裸客户端, 用于验证“绕过页面直接提交同样被拦住”。"""
    return HeaderClient(app)


@pytest.fixture
def client_as(app):
    def _make(token):
        return HeaderClient(app, token)

    return _make


@pytest.fixture
def entry_payload():
    def _make(station_id, measured_at="2026-09-01 10:00", entries=None, **overrides):
        payload = {
            "station_id": station_id,
            "measured_at": measured_at,
            "period": "hourly",
            "entries": entries
            if entries is not None
            else [
                {"pollutant": "PM25", "value": 60.0},
                {"pollutant": "SO2", "value": 900.0},
                {"pollutant": "CO", "value": 1.2},
            ],
        }
        payload.update(overrides)
        return payload

    return _make


@pytest.fixture
def station_model():
    return Station

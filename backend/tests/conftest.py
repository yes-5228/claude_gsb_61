from datetime import datetime, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import Position, PositionScopeVersion, Station, User
from app.services import auth_service, station_service


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


def _make_scope(position, stations=None, pollutants=None, all_stations=True,
                all_pollutants=True, effective_from=None):
    version = PositionScopeVersion(
        position_id=position.id,
        effective_from=effective_from or (datetime.now() - timedelta(days=1)),
        all_stations=all_stations,
        all_pollutants=all_pollutants,
    )
    version.station_codes = stations or []
    version.pollutant_codes = pollutants or []
    db.session.add(version)
    return version


def _make_user(username, display, position, password="test123456", active=True):
    user = User(username=username, display_name=display, position=position, active=active)
    user.set_password(password)
    db.session.add(user)
    return user


@pytest.fixture
def identities(app):
    """岗位 + 用户 + 范围版本; 返回 username -> User。"""
    admin_pos = Position(code="admin", name="系统管理员", is_admin=True, can_proxy=True)
    full_pos = Position(code="full", name="综合录入岗", can_proxy=True)
    site_pos = Position(code="site", name="单站点录入岗", can_proxy=True)
    gas_pos = Position(code="gas", name="气态污染物岗", can_proxy=False)
    pm_pos = Position(code="pm", name="颗粒物岗", can_proxy=False)
    db.session.add_all([admin_pos, full_pos, site_pos, gas_pos, pm_pos])
    db.session.flush()

    _make_scope(full_pos)
    _make_scope(site_pos, stations=["TEST-001"], all_stations=False)
    _make_scope(gas_pos, stations=["TEST-001", "TEST-002"],
                pollutants=["SO2", "NO2", "CO", "O3"],
                all_stations=False, all_pollutants=False)
    _make_scope(pm_pos, all_stations=True, pollutants=["PM25", "PM10"],
                all_pollutants=False)
    db.session.flush()

    users = {
        "admin": _make_user("admin", "管理员", admin_pos),
        "full": _make_user("full", "全权员", full_pos),
        "site": _make_user("site", "单站员", site_pos),
        "gas": _make_user("gas", "气态员", gas_pos),
        "pm": _make_user("pm", "颗粒员", pm_pos),
        "disabled": _make_user("disabled", "停用员", site_pos, active=False),
    }
    db.session.commit()
    return users


@pytest.fixture
def client(app, identities):
    """默认携带管理员令牌的测试客户端; 可用 login_as 切换。"""
    test_client = app.test_client()

    def login_as(username, password="test123456"):
        if username is None:
            test_client.environ_base.pop("HTTP_AUTHORIZATION", None)
            return
        if username in identities:
            user = identities[username]
            _, token = auth_service.authenticate(user.username, password)
        else:
            resp = test_client.post("/api/auth/login",
                                    json={"username": username, "password": password})
            assert resp.status_code == 200, resp.get_data(as_text=True)
            token = resp.get_json()["token"]
        test_client.environ_base["HTTP_AUTHORIZATION"] = "Bearer " + token

    def add_scope(position, **kwargs):
        version = _make_scope(position, **kwargs)
        db.session.commit()
        return version.id

    test_client.login_as = login_as
    test_client.add_scope = add_scope
    test_client.positions = {
        "admin": identities["admin"].position,
        "full": identities["full"].position,
        "site": identities["site"].position,
        "gas": identities["gas"].position,
        "pm": identities["pm"].position,
    }
    login_as("admin")
    return test_client


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
def entry_payload():
    def _make(station_id, measured_at="2026-09-01 10:00", entries=None, **overrides):
        payload = {
            "station_id": station_id,
            "measured_at": measured_at,
            "period": "hourly",
            "data_source": "manual",
            "recorder": "测试员",
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

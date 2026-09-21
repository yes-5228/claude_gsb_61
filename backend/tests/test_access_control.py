"""岗位录入权限测试: 范围收窄、越权拦截、代录标注、口径生效时间、停用/调岗实时生效。"""
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Measurement, Position, PositionScope, ScopePollutant, User


def _entry(station_id, *pollutants, measured_at="2026-09-01 10:00"):
    return {
        "station_id": station_id,
        "measured_at": measured_at,
        "period": "hourly",
        "entries": [{"pollutant": code, "value": 30.0} for code in pollutants],
    }


# ---------------- 未登录拦截 (绕过页面直接提交) ----------------

def test_submission_without_login_is_rejected(anon_client, station):
    response = anon_client.post("/api/measurements/entries", json=_entry(station.id, "PM25"))
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHORIZED"
    assert Measurement.query.count() == 0


def test_forged_operator_header_is_rejected(anon_client, station):
    response = anon_client.post(
        "/api/measurements/entries",
        json=_entry(station.id, "PM25"),
        headers={"X-Operator-Token": "not-a-real-token"},
    )
    assert response.status_code == 401


def test_preview_without_login_is_rejected(anon_client, station):
    response = anon_client.post(
        "/api/measurements/preview",
        json={"period": "hourly", "entries": [{"pollutant": "PM25", "value": 1}]},
    )
    assert response.status_code == 401


def test_client_supplied_recorder_and_data_source_are_ignored(client, station):
    """请求体伪造录入人/来源不会生效, 一律以登录身份与服务端口径带出。"""
    payload = _entry(station.id, "PM25")
    payload["recorder"] = "伪造的录入人"
    payload["data_source"] = "device"
    response = client.post("/api/measurements/entries", json=payload)
    assert response.status_code == 201
    record = Measurement.query.one()
    assert record.recorder == "管理员"
    assert record.data_source == "manual"


# ---------------- 点位范围越权 ----------------

def test_station_out_of_scope_is_blocked(client_as, scoped_operator, second_station):
    client = client_as("test-token-operator")
    response = client.post(
        "/api/measurements/entries", json=_entry(second_station.id, "PM25")
    )
    assert response.status_code == 403
    error = response.get_json()["error"]
    assert error["code"] == "PERMISSION_DENIED"
    assert "越权提交被拦截" in error["message"]
    assert "工业园监测点" in error["message"]
    assert Measurement.query.count() == 0


def test_pollutant_out_of_scope_is_blocked(client_as, scoped_operator, station):
    client = client_as("test-token-operator")
    response = client.post(
        "/api/measurements/entries", json=_entry(station.id, "PM25", "CO")
    )
    assert response.status_code == 403
    message = response.get_json()["error"]["message"]
    assert "CO" in message
    assert "因子" in message
    assert Measurement.query.count() == 0


def test_in_scope_submission_succeeds_and_snapshots_scope(client_as, scoped_operator, station):
    client = client_as("test-token-operator")
    response = client.post(
        "/api/measurements/entries", json=_entry(station.id, "PM25", "SO2")
    )
    assert response.status_code == 201
    records = Measurement.query.all()
    assert len(records) == 2
    scope_id = scoped_operator["scope"].id
    assert all(record.scope_id == scope_id for record in records)
    assert all(record.position_id == scoped_operator["position"].id for record in records)


def test_preview_blocks_pollutant_out_of_scope(client_as, scoped_operator, station):
    client = client_as("test-token-operator")
    response = client.post(
        "/api/measurements/preview",
        json={
            "station_id": station.id,
            "period": "hourly",
            "entries": [{"pollutant": "O3", "value": 1}],
        },
    )
    assert response.status_code == 403


def test_entry_context_is_narrowed_to_scope(client_as, scoped_operator, station, second_station):
    client = client_as("test-token-operator")
    body = client.get("/api/measurements/entry-context").get_json()
    assert [item["id"] for item in body["stations"]] == [station.id]
    assert {item["code"] for item in body["pollutants"]} == {"PM25", "SO2"}


# ---------------- 代录 ----------------

def test_proxy_entry_is_marked_with_actual_operator(client_as, scoped_operator, station):
    client = client_as("test-token-operator")
    colleague = scoped_operator["colleague"]
    payload = _entry(station.id, "PM25")
    payload["recorder_id"] = colleague.id
    response = client.post("/api/measurements/entries", json=payload)
    assert response.status_code == 201
    record = Measurement.query.one()
    assert record.recorder_id == colleague.id
    assert record.recorder == "录入员乙"
    assert record.operator_id == scoped_operator["user"].id
    assert record.operator_name == "录入员甲"
    assert record.is_proxy is True
    meta = response.get_json()["submitted_by"]
    assert meta["is_proxy"] is True
    assert meta["operator_name"] == "录入员甲"
    assert meta["recorder_name"] == "录入员乙"


def test_self_entry_is_not_marked_as_proxy(client_as, scoped_operator, station):
    client = client_as("test-token-operator")
    payload = _entry(station.id, "PM25")
    payload["recorder_id"] = scoped_operator["user"].id
    response = client.post("/api/measurements/entries", json=payload)
    assert response.status_code == 201
    record = Measurement.query.one()
    assert record.is_proxy is False


def test_proxy_requires_active_recorder(client_as, scoped_operator, station):
    client = client_as("test-token-operator")
    payload = _entry(station.id, "PM25")
    payload["recorder_id"] = 99999
    response = client.post("/api/measurements/entries", json=payload)
    assert response.status_code == 422


# ---------------- 停用 / 调岗立即生效 ----------------

def test_deactivating_user_tightens_scope_immediately(client_as, scoped_operator, station):
    client = client_as("test-token-operator")
    assert client.post("/api/measurements/entries", json=_entry(station.id, "PM25")).status_code == 201

    scoped_operator["user"].is_active = False
    db.session.commit()

    response = client.post(
        "/api/measurements/entries",
        json=_entry(station.id, "PM25", measured_at="2026-09-01 11:00"),
    )
    assert response.status_code == 403
    assert "停用" in response.get_json()["error"]["message"]


def test_deactivating_position_tightens_scope_immediately(client_as, scoped_operator, station):
    client = client_as("test-token-operator")
    scoped_operator["position"].is_active = False
    db.session.commit()
    response = client.post("/api/measurements/entries", json=_entry(station.id, "PM25"))
    assert response.status_code == 403
    assert "岗位" in response.get_json()["error"]["message"]


def test_position_transfer_tightens_scope_immediately(app, client_as, scoped_operator,
                                                      auth_data, station, second_station):
    client = client_as("test-token-operator")
    # 调岗前只能录 TEST-001
    assert client.post(
        "/api/measurements/entries", json=_entry(station.id, "PM25")
    ).status_code == 201

    # 调岗到“二区录入员”, 该岗位还没有任何生效口径 -> 立即失去录入权
    scoped_operator["user"].position_id = auth_data["other_pos"].id
    db.session.commit()
    response = client.post(
        "/api/measurements/entries",
        json=_entry(station.id, "PM25", measured_at="2026-09-01 12:00"),
    )
    assert response.status_code == 403


def test_user_without_position_is_denied(app, auth_data, station):
    user = User(username="lonely", name="无岗人员", token=User.generate_token(),
                is_active=True, position_id=None)
    db.session.add(user)
    db.session.commit()
    client = app.test_client()
    response = client.post(
        "/api/measurements/entries",
        json=_entry(station.id, "PM25"),
        headers={"X-Operator-Token": user.token},
    )
    assert response.status_code == 403
    assert "尚未分配岗位" in response.get_json()["error"]["message"]


# ---------------- 口径生效时间: 只影响此后录入, 历史归属不变 ----------------

def test_scope_adjustment_only_affects_future_entries(app, client_as, scoped_operator, station):
    client = client_as("test-token-operator")
    old_scope = scoped_operator["scope"]

    # 调整前录入一条 (点位在范围内)
    before = client.post(
        "/api/measurements/entries", json=_entry(station.id, "PM25")
    )
    assert before.status_code == 201

    # 明天生效的新版口径: 去掉 PM25
    future = datetime.now() + timedelta(days=1)
    new_scope = PositionScope(
        position_id=scoped_operator["position"].id,
        effective_from=future,
        all_stations=False, all_pollutants=False, remark="收紧: 仅 SO2",
    )
    db.session.add(new_scope)
    db.session.flush()
    new_scope.stations = [station]
    new_scope.pollutant_codes = [ScopePollutant(pollutant="SO2")]
    db.session.commit()

    # 未来版本尚未生效: 现在提交 PM25 仍然按旧口径放行
    now_ok = client.post(
        "/api/measurements/entries",
        json=_entry(station.id, "PM25", measured_at="2026-09-01 13:00"),
    )
    assert now_ok.status_code == 201

    # 生效时间之后提交: 按新口径, PM25 被拦
    later = datetime.now() + timedelta(days=2)
    from app.services import access_service

    with _freeze_time(later):
        response = client.post(
            "/api/measurements/entries",
            json=_entry(station.id, "PM25", measured_at="2026-09-03 09:00"),
        )
    assert response.status_code == 403

    # SO2 在新口径下仍可录入, 且快照指向新版本
    with _freeze_time(later):
        ok = client.post(
            "/api/measurements/entries",
            json=_entry(station.id, "SO2", measured_at="2026-09-03 10:00"),
        )
    assert ok.status_code == 201
    new_record = Measurement.query.filter(
        Measurement.measured_at == datetime(2026, 9, 3, 10, 0)
    ).one()
    assert new_record.scope_id == new_scope.id

    # 历史记录归属仍是登记当时的旧口径
    historical = Measurement.query.filter(
        Measurement.measured_at == datetime(2026, 9, 1, 10, 0)
    ).one()
    assert historical.scope_id == old_scope.id


class _freeze_time:
    """临时把岗位取口径的“当前时刻”固定到指定时间。"""

    def __init__(self, frozen):
        self.frozen = frozen
        self.original = None

    def __enter__(self):
        from app.models.position import Position

        self.original = Position.current_scope

        def current_scope(position_self, at=None):
            return self.original(position_self, at=self.frozen)

        Position.current_scope = current_scope
        return self

    def __exit__(self, *exc):
        from app.models.position import Position

        Position.current_scope = self.original


def test_duplicate_effective_from_is_conflict(client, auth_data, station):
    payload = {
        "effective_from": "2026-09-20 09:00",
        "all_stations": False,
        "all_pollutants": False,
        "station_ids": [station.id],
        "pollutants": ["PM25"],
    }
    url = "/api/admin/positions/%d/scopes" % auth_data["op_pos"].id
    first = client.post(url, json=payload)
    assert first.status_code == 201
    second = client.post(url, json=payload)
    assert second.status_code == 409


# ---------------- 管理员接口 ----------------

def test_admin_endpoints_denied_for_non_admin(client_as, scoped_operator):
    client = client_as("test-token-operator")
    assert client.get("/api/admin/positions").status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_admin_can_create_position_scope_and_user(client, auth_data, station):
    create_pos = client.post(
        "/api/admin/positions",
        json={"code": "NEW_OP", "name": "新岗位", "description": "接口创建"},
    )
    assert create_pos.status_code == 201
    position_id = create_pos.get_json()["id"]

    create_scope = client.post(
        "/api/admin/positions/%d/scopes" % position_id,
        json={
            "effective_from": "2026-09-01 00:00",
            "station_ids": [station.id],
            "pollutants": ["NO2", "O3"],
        },
    )
    assert create_scope.status_code == 201
    scope_body = create_scope.get_json()
    assert scope_body["station_ids"] == [station.id]
    assert sorted(scope_body["pollutants"]) == ["NO2", "O3"]

    create_user = client.post(
        "/api/admin/users",
        json={"username": "newbie", "name": "新人", "position_id": position_id},
    )
    assert create_user.status_code == 201
    assert create_user.get_json()["token"]


def test_transfer_via_admin_api_takes_effect_immediately(client, scoped_operator,
                                                        auth_data, station):
    user = scoped_operator["user"]
    response = client.put(
        "/api/admin/users/%d" % user.id,
        json={"position_id": auth_data["other_pos"].id},
    )
    assert response.status_code == 200
    db.session.expire_all()
    assert user.position_id == auth_data["other_pos"].id


def test_admin_scope_requires_explicit_ranges(client, auth_data):
    response = client.post(
        "/api/admin/positions/%d/scopes" % auth_data["op_pos"].id,
        json={"effective_from": "2026-09-01 00:00", "station_ids": [], "pollutants": []},
    )
    assert response.status_code == 422


def test_overwrite_keeps_historical_attribution(client_as, scoped_operator, station):
    """覆盖更新只改数据值, 首次录入的口径归属与名义录入人保留。"""
    client = client_as("test-token-operator")
    colleague = scoped_operator["colleague"]
    first = _entry(station.id, "PM25")
    first["recorder_id"] = colleague.id
    first["entries"] = [{"pollutant": "PM25", "value": 30.0}]
    client.post("/api/measurements/entries", json=first)

    record = Measurement.query.one()
    old_scope = record.scope_id

    overwrite = _entry(station.id, "PM25")
    overwrite["overwrite"] = True
    overwrite["entries"] = [{"pollutant": "PM25", "value": 42.0}]
    client.post("/api/measurements/entries", json=overwrite)

    db.session.expire_all()
    record = Measurement.query.one()
    assert record.value == 42.0
    assert record.scope_id == old_scope  # 历史口径归属不变
    assert record.recorder_id == colleague.id  # 名义录入人不变

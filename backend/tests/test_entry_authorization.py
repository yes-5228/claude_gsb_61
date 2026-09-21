"""岗位录入范围 / 登录 / 代录 / 范围版本生效时间的端到端测试。"""
from datetime import datetime, timedelta

from app.models import Measurement, User

PM_ONLY = [{"pollutant": "PM25", "value": 60.0}]
GAS = [{"pollutant": "SO2", "value": 900.0}]
MIX = [
    {"pollutant": "PM25", "value": 60.0},
    {"pollutant": "SO2", "value": 900.0},
]


# --------------------------------------------------------------- 登录鉴权
def test_login_success_returns_token_and_scope(client, identities):
    response = client.post("/api/auth/login", json={"username": "site", "password": "test123456"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["token"]
    assert body["user"]["display_name"] == "单站员"
    assert body["user"]["scope"]["station_codes"] == ["TEST-001"]


def test_login_wrong_password_rejected(client):
    response = client.post("/api/auth/login", json={"username": "site", "password": "bad"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "BAD_CREDENTIALS"


def test_disabled_user_cannot_login(client):
    response = client.post("/api/auth/login",
                           json={"username": "disabled", "password": "test123456"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_submit_without_token_is_unauthorized(client, station, entry_payload):
    client.login_as(None)
    response = client.post("/api/measurements/entries", json=entry_payload(station.id, entries=PM_ONLY))
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_forged_token_is_rejected(client, station, entry_payload):
    client.environ_base["HTTP_AUTHORIZATION"] = "Bearer not-a-real-token"
    response = client.post("/api/measurements/entries", json=entry_payload(station.id, entries=PM_ONLY))
    assert response.status_code == 401


# ----------------------------------------------------------- 点位范围越权
def test_out_of_scope_station_is_blocked(client, station, second_station, entry_payload):
    client.login_as("site")  # 只能录 TEST-001
    response = client.post(
        "/api/measurements/entries",
        json=entry_payload(second_station.id, entries=PM_ONLY),
    )
    assert response.status_code == 403
    error = response.get_json()["error"]
    assert error["code"] == "OUT_OF_SCOPE"
    assert "TEST-002" in error["message"]
    assert "不在可录入范围" in error["message"]
    assert error["fields"]["station_id"] == "out_of_scope"


def test_out_of_scope_pollutant_is_blocked(client, station, entry_payload):
    client.login_as("pm")  # 只能录颗粒物
    response = client.post(
        "/api/measurements/entries", json=entry_payload(station.id, entries=MIX)
    )
    assert response.status_code == 403
    error = response.get_json()["error"]
    assert "SO2" in error["message"]
    assert error["fields"]["SO2"] == "out_of_scope"
    assert Measurement.query.count() == 0  # 整批拒绝, 不写入任何一条


def test_gas_position_blocked_on_pm_station_ok(client, station, entry_payload):
    client.login_as("gas")  # TEST-001 + 气态因子
    ok = client.post(
        "/api/measurements/entries", json=entry_payload(station.id, entries=GAS)
    )
    assert ok.status_code == 201
    blocked = client.post(
        "/api/measurements/entries", json=entry_payload(station.id, entries=PM_ONLY)
    )
    assert blocked.status_code == 403


def test_preview_also_enforces_scope(client, second_station, entry_payload):
    client.login_as("site")
    response = client.post(
        "/api/measurements/preview",
        json=entry_payload(second_station.id, entries=PM_ONLY),
    )
    assert response.status_code == 403


def test_entry_context_lists_only_scoped_options(client, station, second_station):
    client.login_as("site")
    body = client.get("/api/measurements/entry-context").get_json()
    assert [item["code"] for item in body["stations"]] == ["TEST-001"]
    client.login_as("pm")
    body = client.get("/api/measurements/entry-context").get_json()
    assert body["pollutant_codes"] == ["PM25", "PM10"]


# ----------------------------------------------- 绕过页面直连接口同样拦截
def test_direct_api_post_is_blocked_like_page(client, station, entry_payload):
    """不经过任何页面, 手工构造越权请求体 (含伪造 recorder/来源) 仍被拦截。"""
    client.login_as("pm")  # 只能录颗粒物
    payload = entry_payload(station.id, entries=GAS)
    payload["recorder"] = "随便填的管理员"   # 试图把自己伪装成别人
    payload["data_source"] = "device"      # 试图伪造数据来源
    response = client.post("/api/measurements/entries", json=payload)
    assert response.status_code == 403
    assert Measurement.query.count() == 0


# ------------------------------------------------------- 停用/调岗即时生效
def test_deactivating_position_tightens_scope_immediately(client, app, station,
                                                          identities, entry_payload):
    client.login_as("site")
    assert client.post("/api/measurements/entries",
                       json=entry_payload(station.id, entries=PM_ONLY)).status_code == 201

    position = identities["site"].position
    position.active = False
    from app.extensions import db
    db.session.commit()

    # 调岗/停用后令牌并未失效, 但实时查库立即收紧: 录入与再请求均被拒
    response = client.post("/api/measurements/entries",
                           json=entry_payload(station.id, entries=PM_ONLY))
    assert response.status_code == 401


def test_user_transfer_immediately_changes_scope(client, app, station, second_station,
                                                 identities, entry_payload):
    client.login_as("site")  # 原本只能 TEST-001
    site_user = User.query.filter_by(username="site").one()
    site_user.position = identities["full"].position  # 调到全量岗
    from app.extensions import db
    db.session.commit()

    response = client.post(
        "/api/measurements/entries",
        json=entry_payload(second_station.id, entries=PM_ONLY),
    )
    assert response.status_code == 201  # 调岗后新范围立即放开


# ------------------------------------------------------- 范围版本生效时间
def test_scope_version_only_affects_entries_after_effective_time(
    client, app, station, second_station, identities, entry_payload
):
    # site 岗新增"未来生效"的放开版本: 现在仍不能录 TEST-002
    future = datetime.now() + timedelta(days=2)
    response = client.post(
        "/api/admin/positions/%d/scope-versions" % identities["site"].position_id,
        json={
            "effective_from": future.strftime("%Y-%m-%d %H:%M"),
            "all_stations": True,
            "all_pollutants": True,
        },
    )
    assert response.status_code == 201

    client.login_as("site")
    blocked_now = client.post(
        "/api/measurements/entries",
        json=entry_payload(second_station.id, entries=PM_ONLY),
    )
    assert blocked_now.status_code == 403

    # 补一条"过去生效"的收紧/放开版本: 立即生效, TEST-002 可录
    client.login_as("admin")
    client.post(
        "/api/admin/positions/%d/scope-versions" % identities["site"].position_id,
        json={
            "effective_from": (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
            "all_stations": True,
            "all_pollutants": True,
        },
    )
    client.login_as("site")
    allowed = client.post(
        "/api/measurements/entries",
        json=entry_payload(second_station.id, entries=PM_ONLY),
    )
    assert allowed.status_code == 201


def test_historical_record_keeps_scope_snapshot_after_range_change(
    client, app, station, identities, entry_payload
):
    client.login_as("site")
    created = client.post(
        "/api/measurements/entries", json=entry_payload(station.id, entries=PM_ONLY)
    ).get_json()
    old_version_id = created["submission"]["scope_version_id"]
    assert old_version_id is not None

    stored = Measurement.query.filter_by(pollutant="PM25").one()
    assert stored.scope_version_id == old_version_id
    assert stored.scope_position_id == identities["site"].position_id

    # 之后再发布新版本, 历史记录的口径快照不变
    client.login_as("admin")
    new_version_id = client.add_scope(
        identities["site"].position,
        stations=["TEST-001"], pollutants=["SO2"],
        all_stations=False, all_pollutants=False,
        effective_from=datetime.now() - timedelta(seconds=1),
    )
    stored = Measurement.query.filter_by(pollutant="PM25").one()
    assert stored.scope_version_id == old_version_id
    assert stored.scope_version_id != new_version_id


# ------------------------------------------------------------- 代录
def test_proxy_entry_records_actual_operator(client, station, identities, entry_payload):
    # full 岗位允许代录; 代 site(单站员) 录入其范围内点位
    client.login_as("full")
    response = client.post(
        "/api/measurements/entries",
        json=entry_payload(station.id, entries=PM_ONLY,
                           on_behalf_of_id=identities["site"].id),
    )
    assert response.status_code == 201
    sub = response.get_json()["submission"]
    assert sub["recorder"] == "单站员"
    assert sub["operator"] == "全权员"
    assert sub["is_proxy"] is True

    stored = Measurement.query.filter_by(pollutant="PM25").one()
    assert stored.recorder == "单站员"
    assert stored.recorder_id == identities["site"].id
    assert stored.operator_id == identities["full"].id
    assert stored.is_proxy is True


def test_proxy_denied_for_position_without_proxy_right(client, station, identities, entry_payload):
    # pm 岗位无代录权限, 即使目标合法也被拦
    client.login_as("pm")
    response = client.post(
        "/api/measurements/entries",
        json=entry_payload(station.id, entries=PM_ONLY,
                           on_behalf_of_id=identities["site"].id),
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "PROXY_FORBIDDEN"


def test_proxy_still_subject_to_operator_scope(client, second_station, identities, entry_payload):
    # full 可代录但站点仍按 full 范围(全量) -> 允许; 换成 site 代录 TEST-002 -> 越权
    client.login_as("site")
    response = client.post(
        "/api/measurements/entries",
        json=entry_payload(second_station.id, entries=PM_ONLY,
                           on_behalf_of_id=identities["full"].id),
    )
    assert response.status_code == 403  # 操作人 site 不能录 TEST-002


# ----------------------------------------------------------- 来源/时间自动
def test_recorder_time_source_are_server_assigned_and_client_ignored(
    client, station, entry_payload
):
    client.login_as("site")
    before = datetime.now()
    payload = entry_payload(station.id, entries=PM_ONLY,
                            recorder="伪造录入人", data_source="import")
    response = client.post("/api/measurements/entries", json=payload)
    assert response.status_code == 201
    stored = Measurement.query.filter_by(pollutant="PM25").one()
    assert stored.recorder == "单站员"          # 忽略伪造
    assert stored.data_source == "manual"       # 手工录入固定
    assert stored.submitted_at is not None and stored.submitted_at >= before


# -------------------------------------------------------------- 管理权限
def test_admin_only_endpoints_reject_non_admin(client, identities):
    client.login_as("site")
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/positions").status_code == 403
    assert client.post("/api/admin/users", json={}).status_code == 403


def test_admin_creates_user_and_position(client, station, second_station):
    body = client.post(
        "/api/admin/positions",
        json={
            "code": "newscope", "name": "新岗位",
            "scope": {
                "all_stations": False, "station_codes": ["TEST-002"],
                "all_pollutants": True,
            },
        },
    ).get_json()
    position_id = body["id"]
    assert body["current_scope"]["station_codes"] == ["TEST-002"]

    user = client.post(
        "/api/admin/users",
        json={"username": "newguy", "display_name": "新人",
              "password": "secret123", "position_id": position_id},
    ).get_json()
    assert user["scope"]["station_codes"] == ["TEST-002"]

    client.login_as("newguy", password="secret123")
    assert client.post(
        "/api/measurements/entries",
        json={"station_id": station.id, "measured_at": "2026-09-01 10:00",
              "period": "hourly", "entries": PM_ONLY},
    ).status_code == 403
    assert client.post(
        "/api/measurements/entries",
        json={"station_id": second_station.id, "measured_at": "2026-09-01 10:00",
              "period": "hourly", "entries": PM_ONLY},
    ).status_code == 201

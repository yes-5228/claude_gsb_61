"""演示数据生成与启动引导."""
import random
from datetime import date, datetime, timedelta

from .extensions import db
from .models import Exceedance, Measurement, Position, PositionScopeVersion, Station, User
from .models.identity import DEFAULT_PASSWORD

DEMO_STATIONS = [
    {
        "code": "SZ-AQ-001", "name": "市民中心站", "area": "福田区",
        "address": "福田区福中三路市民中心广场", "station_type": "ambient",
        "status": "active", "longitude": 114.0579, "latitude": 22.5410,
        "installed_at": date(2019, 5, 12), "remark": "城市环境评价点",
    },
    {
        "code": "SZ-AQ-002", "name": "华侨城站", "area": "南山区",
        "address": "南山区华侨城生态广场", "station_type": "ambient",
        "status": "active", "longitude": 113.9711, "latitude": 22.5356,
        "installed_at": date(2020, 3, 1), "remark": "城市环境评价点",
    },
    {
        "code": "SZ-AQ-003", "name": "罗湖口岸站", "area": "罗湖区",
        "address": "罗湖区火车站东广场", "station_type": "traffic",
        "status": "active", "longitude": 114.1276, "latitude": 22.5329,
        "installed_at": date(2018, 11, 20), "remark": "道路交通监测点, 早晚高峰浓度偏高",
    },
    {
        "code": "SZ-AQ-004", "name": "宝安中心站", "area": "宝安区",
        "address": "宝安区中心区宝安大道", "station_type": "ambient",
        "status": "active", "longitude": 113.8830, "latitude": 22.5551,
        "installed_at": date(2021, 6, 18), "remark": None,
    },
    {
        "code": "SZ-AQ-005", "name": "龙岗工业园站", "area": "龙岗区",
        "address": "龙岗区宝龙工业区龙岗大道", "station_type": "industrial",
        "status": "active", "longitude": 114.2465, "latitude": 22.7204,
        "installed_at": date(2019, 9, 8), "remark": "周边为工业排放源, 需重点关注 SO₂",
    },
    {
        "code": "SZ-AQ-006", "name": "梧桐山背景站", "area": "罗湖区",
        "address": "罗湖区梧桐山风景区", "station_type": "background",
        "status": "active", "longitude": 114.1837, "latitude": 22.5862,
        "installed_at": date(2017, 4, 2), "remark": "区域背景点, 用于对照评价",
    },
    {
        "code": "SZ-AQ-007", "name": "大鹏生态站", "area": "大鹏新区",
        "address": "大鹏新区葵涌街道", "station_type": "rural",
        "status": "maintenance", "longitude": 114.4798, "latitude": 22.5964,
        "installed_at": date(2022, 8, 15), "remark": "设备检修中, 计划本周恢复",
    },
    {
        "code": "SZ-AQ-008", "name": "前海自贸区站", "area": "南山区",
        "address": "南山区前海湾保税港区", "station_type": "ambient",
        "status": "offline", "longitude": 113.8980, "latitude": 22.5253,
        "installed_at": date(2023, 1, 10), "remark": "站点搬迁停用",
    },
]

POLLUTANT_BASE = {"PM25": 45.0, "PM10": 80.0, "SO2": 30.0, "NO2": 45.0, "CO": 1.5, "O3": 120.0}
HOURLY_FACTOR = {"PM25": 1.0, "PM10": 1.05, "SO2": 0.8, "NO2": 1.1, "CO": 0.9, "O3": 1.3}
STATION_FACTOR = {
    "ambient": 1.0, "traffic": 1.2, "industrial": 1.35, "background": 0.55, "rural": 0.75,
}
HOURLY_POINTS = (2, 8, 14, 20)
RECORDERS = ("李静", "王敏", "陈志强", "赵宇", "孙倩")

# (账号, 姓名, 岗位编码, 是否启用)
SEED_USERS = [
    ("admin", "系统管理员", "admin", True),
    ("lijing", "李静", "full", True),
    ("wangmin", "王敏", "futian", True),
    ("chenzq", "陈志强", "industrial", True),
    ("zhaoyu", "赵宇", "particulate", True),
    ("sunqian", "孙倩", "futian", False),  # 已停用, 便于演示停用后立即不能录入
]


def seed_identities():
    """创建岗位(含带生效时间的范围版本)与登录账号, 返回 username -> User。"""
    admin_pos = Position(code="admin", name="系统管理员", is_admin=True, can_proxy=True,
                         remark="不做点位/因子限制, 可管理人员与范围")
    full_pos = Position(code="full", name="综合录入岗", can_proxy=True,
                        remark="全部点位、全部因子, 允许代录")
    futian_pos = Position(code="futian", name="福田站点录入岗",
                          remark="仅市民中心站, 全部因子")
    industrial_pos = Position(code="industrial", name="工业园专项岗",
                              remark="仅工业园站, 气态污染物因子")
    particulate_pos = Position(code="particulate", name="颗粒物专项岗",
                               remark="全部点位, 仅 PM2.5 / PM10")
    db.session.add_all([admin_pos, full_pos, futian_pos, industrial_pos, particulate_pos])
    db.session.flush()

    now = datetime.now()
    past = now - timedelta(days=400)  # 让历史演示数据也落在某个已生效版本内

    def scope(position, stations=None, pollutants=None, all_stations=True,
              all_pollutants=True, effective_from=None, remark=None):
        version = PositionScopeVersion(
            position_id=position.id, effective_from=effective_from or past,
            all_stations=all_stations, all_pollutants=all_pollutants, remark=remark,
        )
        version.station_codes = stations or []
        version.pollutant_codes = pollutants or []
        db.session.add(version)
        return version

    scope(full_pos, all_stations=True, all_pollutants=True, remark="全量")
    scope(futian_pos, stations=["SZ-AQ-001"], all_stations=False, all_pollutants=True,
          remark="市民中心站")
    scope(industrial_pos, stations=["SZ-AQ-005"],
          pollutants=["SO2", "NO2", "CO", "O3"],
          all_stations=False, all_pollutants=False, remark="气态污染物")
    scope(particulate_pos, all_stations=True, pollutants=["PM25", "PM10"],
          all_pollutants=False, remark="颗粒物两项")
    db.session.flush()

    position_by_code = {p.code: p for p in (admin_pos, full_pos, futian_pos,
                                            industrial_pos, particulate_pos)}
    users = {}
    for username, display, pos_code, active in SEED_USERS:
        user = User(username=username, display_name=display,
                    position=position_by_code[pos_code], active=active,
                    remark=("演示停用账号" if not active else None))
        user.set_password(DEFAULT_PASSWORD)
        db.session.add(user)
        users[username] = user
    db.session.commit()
    return users


def _value(pollutant, period, station_type, rng):
    base = POLLUTANT_BASE[pollutant] * STATION_FACTOR.get(station_type, 1.0)
    if period == "hourly":
        base *= HOURLY_FACTOR[pollutant]
    value = base * rng.uniform(0.72, 1.22)
    if rng.random() < 0.12:  # 少量明显超标样本, 便于演示超标标注
        value *= rng.uniform(1.8, 2.6)
    return round(value, 2 if pollutant == "CO" else 1)


def seed_demo_data(days=5, rng=None, recorder_pool=RECORDERS):
    """Generate demo stations and monitoring records through the normal service path."""
    from .services import measurement_service

    users = seed_identities()
    # 综合录入岗/管理员拥有全量范围, 用于批量生成历史演示数据
    system_operator = users.get("admin")
    recorder_users = [users[name] for name in ("lijing", "wangmin", "chenzq", "zhaoyu")
                      if name in users]

    rng = rng or random.Random(20260914)
    created_stations = []
    for item in DEMO_STATIONS:
        station = Station(**item)
        db.session.add(station)
        created_stations.append(station)
    db.session.commit()

    today = date.today()
    totals = {"stations": len(created_stations), "measurements": 0, "exceedances": 0}
    for station in created_stations:
        for offset in range(days):
            day = today - timedelta(days=offset)
            daily_entries = [
                {"pollutant": code, "value": _value(code, "daily", station.station_type, rng)}
                for code in POLLUTANT_BASE
            ]
            result = measurement_service.record_entries(
                station_id=station.id,
                measured_at=datetime(day.year, day.month, day.day, 0, 0),
                period="daily",
                entries=daily_entries,
                operator=system_operator,
                data_source="device",
                remark="日均值自动汇总",
            )
            totals["measurements"] += result["summary"]["created_count"]
            totals["exceedances"] += result["summary"]["exceeded_count"]

            for hour in HOURLY_POINTS:
                hourly_entries = [
                    {"pollutant": code, "value": _value(code, "hourly", station.station_type, rng)}
                    for code in HOURLY_FACTOR
                ]
                result = measurement_service.record_entries(
                    station_id=station.id,
                    measured_at=datetime(day.year, day.month, day.day, hour, 0),
                    period="hourly",
                    entries=hourly_entries,
                    operator=system_operator,
                    data_source="manual",
                )
                totals["measurements"] += result["summary"]["created_count"]
                totals["exceedances"] += result["summary"]["exceeded_count"]

    # 标注一部分超标记录, 让工作台同时存在待办与已处理记录
    from .services import exceedance_service

    exceedances = Exceedance.query.order_by(Exceedance.id.asc()).all()
    annotated = 0
    for index, record in enumerate(exceedances):
        if index % 3 == 0:
            continue
        if index % 3 == 1:
            exceedance_service.annotate(
                record, status="confirmed", note="数据经复核属实, 已通知运维排查周边排放源",
                annotator=rng.choice(recorder_pool),
            )
        else:
            exceedance_service.annotate(
                record, status="ignored", note="仪器校准期间异常值, 已在原始数据中标记无效",
                annotator=rng.choice(recorder_pool),
            )
        annotated += 1
    totals["annotated"] = annotated
    return totals


def reset_database():
    db.drop_all()
    db.create_all()


def ensure_bootstrap(app):
    """Create tables / seed demo data at startup when enabled by config."""
    auto_init = app.config.get("AUTO_INIT_DB")
    auto_seed = app.config.get("AUTO_SEED")
    if not auto_init and not auto_seed:
        return
    with app.app_context():
        try:
            if auto_init:
                db.create_all()
            if auto_seed and db.session.query(Station.id).first() is None:
                app.logger.info("seeding demo data ...")
                seed_demo_data()
        except Exception as exc:  # pragma: no cover - depends on external database
            app.logger.warning("bootstrap skipped: %s", exc)

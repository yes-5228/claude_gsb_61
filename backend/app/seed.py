"""演示数据生成与启动引导."""
import random
from datetime import date, datetime, timedelta

from .extensions import db
from .models import Exceedance, Measurement, Position, PositionScope, ScopePollutant, Station, User

# 演示岗位 / 人员 (令牌固定, 便于直接使用)
DEMO_POSITIONS = [
    {
        "code": "ADMIN", "name": "系统管理员",
        "description": "负责岗位与录入权限配置, 不直接承担点位录入",
        "all_stations": True, "all_pollutants": True,
    },
    {
        "code": "FUTIAN_OP", "name": "福田区录入员",
        "description": "仅可录入市民中心站的常规气态因子",
        "station_codes": ["SZ-AQ-001"],
        "pollutants": ["SO2", "NO2", "CO", "O3"],
    },
    {
        "code": "NANSHAN_OP", "name": "南山区录入员",
        "description": "可录入南山片区站点的全部因子",
        "station_codes": ["SZ-AQ-002", "SZ-AQ-008"],
        "pollutants": None,  # None 表示全部因子
    },
    {
        "code": "PM_ONLY", "name": "颗粒物专员",
        "description": "各点位仅可录入 PM2.5 / PM10",
        "station_codes": None,  # None 表示全部点位
        "pollutants": ["PM25", "PM10"],
    },
    {
        "code": "READONLY", "name": "停用观察岗",
        "description": "岗位停用后其成员立即失去全部录入权限",
        "station_codes": [],
        "pollutants": [],
        "inactive": True,
    },
]

DEMO_USERS = [
    # username, name, position_code, is_admin, is_active
    ("admin", "管理员", "ADMIN", True, True),
    ("lijing", "李静", "FUTIAN_OP", False, True),
    ("wangmin", "王敏", "NANSHAN_OP", False, True),
    ("chenzq", "陈志强", "PM_ONLY", False, True),
    ("zhaoyu", "赵宇", "FUTIAN_OP", False, True),
    ("sunqian", "孙倩", "READONLY", False, False),  # 被停用的账号
]

DEMO_USER_TOKENS = {
    "admin": "demo-token-admin",
    "lijing": "demo-token-lijing",
    "wangmin": "demo-token-wangmin",
    "chenzq": "demo-token-chenzq",
    "zhaoyu": "demo-token-zhaoyu",
    "sunqian": "demo-token-sunqian",
}

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


def _value(pollutant, period, station_type, rng):
    base = POLLUTANT_BASE[pollutant] * STATION_FACTOR.get(station_type, 1.0)
    if period == "hourly":
        base *= HOURLY_FACTOR[pollutant]
    value = base * rng.uniform(0.72, 1.22)
    if rng.random() < 0.12:  # 少量明显超标样本, 便于演示超标标注
        value *= rng.uniform(1.8, 2.6)
    return round(value, 2 if pollutant == "CO" else 1)


def _seed_positions_and_users(stations_by_code):
    """创建演示岗位 (含一版从当下生效的口径) 与人员账号。"""
    positions = {}
    for spec in DEMO_POSITIONS:
        position = Position(
            code=spec["code"], name=spec["name"], description=spec["description"],
            is_active=not spec.get("inactive", False),
        )
        db.session.add(position)
        db.session.flush()

        all_stations = spec.get("station_codes") is None
        all_pollutants = spec.get("pollutants") is None
        scope = PositionScope(
            position_id=position.id,
            effective_from=datetime.now(),
            all_stations=all_stations,
            all_pollutants=all_pollutants,
            remark="初始口径",
        )
        db.session.add(scope)
        db.session.flush()
        if not all_stations:
            scope.stations = [
                stations_by_code[code] for code in spec["station_codes"] if code in stations_by_code
            ]
        if not all_pollutants:
            scope.pollutant_codes = [ScopePollutant(pollutant=code) for code in spec["pollutants"]]
        positions[spec["code"]] = position
    db.session.commit()

    for username, name, position_code, is_admin, is_active in DEMO_USERS:
        db.session.add(
            User(
                username=username, name=name,
                token=DEMO_USER_TOKENS[username],
                is_active=is_active, is_admin=is_admin,
                position_id=positions[position_code].id,
            )
        )
    db.session.commit()


def seed_demo_data(days=5, rng=None, recorder_pool=RECORDERS):
    """Generate demo stations and monitoring records through the normal service path."""
    from .services import measurement_service

    rng = rng or random.Random(20260914)
    created_stations = []
    for item in DEMO_STATIONS:
        station = Station(**item)
        db.session.add(station)
        created_stations.append(station)
    db.session.commit()
    stations_by_code = {station.code: station for station in created_stations}

    _seed_positions_and_users(stations_by_code)

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
                data_source="device",
                recorder=rng.choice(recorder_pool),
                remark="日均值自动汇总",
                enforce_scope=False,
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
                    data_source="import",
                    recorder=rng.choice(recorder_pool),
                    enforce_scope=False,
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

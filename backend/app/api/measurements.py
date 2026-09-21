"""监测数据录入 API."""
from flask import Blueprint, current_app, request

from ..domain.constants import DATA_SOURCE_LABELS, PERIOD_LABELS
from ..domain.standards import POLLUTANTS
from ..services import auth_service, measurement_service, query_service, station_service
from ..utils.pagination import paginate_query
from ..utils.validation import Validator
from .helpers import json_payload, list_payload

bp = Blueprint("measurements", __name__)


def _scoped_station_options(user):
    """按当前登录人的可录入范围过滤下拉点位 (页面层收窄, 服务层仍会强校验)。"""
    options = station_service.option_list()
    if user.position.is_admin:
        return options
    scope = user.position.current_scope()
    if scope is None or not scope.all_stations:
        allowed = set() if scope is None else set(scope.station_codes)
        options = [item for item in options if item.get("code") in allowed]
    return options


def _scoped_pollutants(user):
    if user.position.is_admin:
        return list(POLLUTANTS.keys())
    scope = user.position.current_scope()
    if scope is None:
        return []
    if scope.all_pollutants:
        return list(POLLUTANTS.keys())
    return [code for code in POLLUTANTS.keys() if code in set(scope.pollutant_codes)]


@bp.get("/", strict_slashes=False)
def list_measurements():
    query, filters = query_service.measurement_query(request.args)
    result = paginate_query(query, lambda row: row.to_dict(include_station=True))
    result["summary"] = query_service.summary(filters)
    return result


@bp.get("/summary")
def measurement_summary():
    return query_service.summary(query_service.parse_filters(request.args))


@bp.post("/preview")
def preview():
    """干跑校验: 录入表单实时预览超标情况, 不写库 (同样按岗位范围预检)。"""
    user = auth_service.current_user()
    data = json_payload()
    validator = Validator(data)
    station_id = validator.number("station_id", "监测点", required=True, minimum=1)
    period = validator.choice("period", "数据周期", choices=tuple(PERIOD_LABELS.keys()),
                              required=True, default="hourly")
    validator.raise_if_invalid()
    entries = list_payload("entries", data)
    return measurement_service.preview_entries(
        period or "hourly", entries, operator=user, station_id=int(station_id)
    )


@bp.post("/entries")
def create_entries():
    """一次录入某个监测点在同一时刻的一组因子数据。

    录入人、提交时间、数据来源由服务端依据登录账号自动带出, 请求体中的
    recorder / data_source 一律忽略; 岗位范围校验在服务层完成, 绕过页面
    直连接口同样被拦截。
    """
    user = auth_service.current_user()
    data = json_payload()
    validator = Validator(data)
    station_id = validator.number("station_id", "监测点", required=True, minimum=1)
    measured_at = validator.datetime_field("measured_at", "监测时间", required=True)
    period = validator.choice("period", "数据周期", choices=tuple(PERIOD_LABELS.keys()),
                              required=True, default="hourly")
    remark = validator.text("remark", "备注", required=False, max_length=500)
    overwrite = validator.boolean("overwrite", False)
    on_behalf_of_id = validator.number("on_behalf_of_id", "代录对象", required=False, minimum=1)
    validator.raise_if_invalid("录入信息不合法")

    entries = list_payload("entries", data)
    return measurement_service.record_entries(
        station_id=int(station_id),
        measured_at=measured_at,
        period=period,
        entries=entries,
        operator=user,
        on_behalf_of_id=int(on_behalf_of_id) if on_behalf_of_id else None,
        remark=remark,
        overwrite=bool(overwrite),
        data_source="manual",  # 页面手工录入固定为"手工录入", 不接受前端指定
    ), 201


@bp.get("/export")
def export_measurements():
    from ..utils.csv_export import csv_response

    query, _ = query_service.measurement_query(request.args)
    rows = query.limit(current_app.config["MAX_EXPORT_ROWS"]).all()
    columns = [
        ("站点编码", lambda row: row.station.code if row.station else ""),
        ("站点名称", lambda row: row.station.name if row.station else ""),
        ("所属区域", lambda row: row.station.area if row.station else ""),
        ("监测因子", lambda row: row.pollutant_label()),
        ("数据周期", lambda row: PERIOD_LABELS.get(row.period, row.period)),
        ("监测值", "value"),
        ("单位", "unit"),
        ("限值", "limit_value"),
        ("是否超标", lambda row: "是" if row.is_exceeded else "否"),
        ("超标倍数", "exceed_ratio"),
        ("监测时间", lambda row: row.measured_at.strftime("%Y-%m-%d %H:%M")),
        ("数据来源", lambda row: DATA_SOURCE_LABELS.get(row.data_source, row.data_source)),
        ("录入人", "recorder"),
        ("实际操作人", lambda row: row.operator_name or ""),
        ("是否代录", lambda row: "是" if row.is_proxy else "否"),
        ("提交时间", lambda row: row.submitted_at.strftime("%Y-%m-%d %H:%M") if row.submitted_at else ""),
        ("备注", "remark"),
    ]
    return csv_response(rows, columns, "monitoring_data")


@bp.get("/<int:measurement_id>")
def get_measurement(measurement_id):
    return measurement_service.get_measurement(measurement_id).to_dict(include_station=True)


@bp.delete("/<int:measurement_id>")
def delete_measurement(measurement_id):
    auth_service.current_user()
    measurement = measurement_service.get_measurement(measurement_id)
    payload = measurement_service.delete_measurement(measurement)
    return {"id": payload["id"], "deleted": True}


@bp.get("/entry-context")
def entry_context():
    """Options needed by the entry form in a single round trip (按岗位范围收窄)."""
    user = auth_service.current_user()
    pollutant_codes = _scoped_pollutants(user)
    pollutants = [
        {"value": code, "label": POLLUTANTS[code]["label"]}
        for code in pollutant_codes
    ]
    # 可代录对象: 启用状态的其他人员 (仅当本岗位有代录权限时有意义)
    proxy_targets = []
    if user.position.is_admin or user.position.can_proxy:
        from ..models import User

        proxy_targets = [
            {"value": other.id, "label": "%s(%s)" % (other.display_name, other.position.name)}
            for other in User.query.filter_by(active=True).order_by(User.id.asc()).all()
            if other.position and other.position.active and other.id != user.id
        ]
    return {
        "user": user.to_dict(include_scope=True),
        "stations": _scoped_station_options(user),
        "pollutant_codes": pollutant_codes,
        "pollutants": pollutants,
        "periods": [{"value": key, "label": label} for key, label in PERIOD_LABELS.items()],
        "data_sources": [
            {"value": "manual", "label": DATA_SOURCE_LABELS["manual"]}
        ],
        "can_proxy": bool(user.position.is_admin or user.position.can_proxy),
        "proxy_targets": proxy_targets,
    }

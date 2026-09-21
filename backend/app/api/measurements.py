"""监测数据录入 API."""
from flask import Blueprint, current_app, request

from ..domain.constants import DATA_SOURCE_LABELS, PERIOD_LABELS
from ..domain.standards import get_pollutant
from ..services import access_service, measurement_service, query_service, station_service
from ..utils.pagination import paginate_query
from ..utils.validation import Validator
from .helpers import json_payload, list_payload

bp = Blueprint("measurements", __name__)


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
    """干跑校验: 录入表单实时预览超标情况, 不写库。

    与正式提交同一道身份/范围门禁, 越权因子在预览阶段就被拦住并给出明确提示。
    """
    user = access_service.require_user()
    data = json_payload()
    validator = Validator(data)
    period = validator.choice("period", "数据周期", choices=tuple(PERIOD_LABELS.keys()),
                              required=True, default="hourly")
    station_id = validator.number("station_id", "监测点", required=False, minimum=1)
    validator.raise_if_invalid()
    entries = list_payload("entries", data)

    pollutant_codes = []
    for entry in entries:
        code = str(entry.get("pollutant", "")).upper()
        if get_pollutant(code):
            pollutant_codes.append(code)
    if station_id:
        station = station_service.get_station(int(station_id))
        access_service.authorize_entry(
            user, station.id, pollutant_codes,
            station_name=station.name,
            pollutant_labels={code: get_pollutant(code)["label"] for code in pollutant_codes},
        )
    else:
        # 未指定监测点时至少校验因子是否在可录范围内
        scope = access_service.effective_scope(user)
        if scope is not None and not scope.all_pollutants:
            allowed = set(scope.pollutants)
            blocked = [code for code in pollutant_codes if code not in allowed]
            if blocked:
                from ..errors import PermissionDeniedError

                raise PermissionDeniedError(
                    "越权操作被拦截: 您的岗位「%s」无权预览/录入因子 %s"
                    % (user.position.name, "、".join(blocked)),
                    fields={"pollutants": "out_of_scope"},
                )
    return measurement_service.preview_entries(period or "hourly", entries)


@bp.post("/entries")
def create_entries():
    """一次录入某个监测点在同一时刻的一组因子数据。

    录入人、提交时间、数据来源均由服务端按当前登录身份自动带出, 请求体中的对应字段
    会被忽略; 选择他人作为名义录入人即代录, 系统自动标注实际提交人。
    """
    user = access_service.require_user()
    data = json_payload()
    validator = Validator(data)
    station_id = validator.number("station_id", "监测点", required=True, minimum=1)
    measured_at = validator.datetime_field("measured_at", "监测时间", required=True)
    period = validator.choice("period", "数据周期", choices=tuple(PERIOD_LABELS.keys()),
                              required=True, default="hourly")
    remark = validator.text("remark", "备注", required=False, max_length=500)
    recorder_id = validator.number("recorder_id", "代录对象", required=False, minimum=1)
    overwrite = validator.boolean("overwrite", False)
    validator.raise_if_invalid("录入信息不合法")

    entries = list_payload("entries", data)

    recorder_user = user
    if recorder_id and int(recorder_id) != user.id:
        from ..extensions import db
        from ..models import User

        recorder_user = db.session.get(User, int(recorder_id))
        if recorder_user is None or not recorder_user.is_active:
            from ..errors import ValidationError

            raise ValidationError(
                "代录对象不存在或已停用, 无法以其名义录入", fields={"recorder_id": "invalid"}
            )

    # 页面手工录入通道: 数据来源固定为手工录入, 不信任请求体中的 data_source/recorder
    return measurement_service.record_entries(
        station_id=int(station_id),
        measured_at=measured_at,
        period=period,
        entries=entries,
        data_source="manual",
        remark=remark,
        overwrite=bool(overwrite),
        actor=user,
        recorder_user=recorder_user,
        enforce_scope=True,
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
        ("名义录入人", "recorder"),
        ("是否代录", lambda row: "代录(实际:%s)" % row.operator_name if row.is_proxy else "否"),
        ("提交时间", lambda row: row.submitted_at.strftime("%Y-%m-%d %H:%M") if row.submitted_at else ""),
        ("备注", "remark"),
    ]
    return csv_response(rows, columns, "monitoring_data")


@bp.get("/<int:measurement_id>")
def get_measurement(measurement_id):
    return measurement_service.get_measurement(measurement_id).to_dict(include_station=True)


@bp.delete("/<int:measurement_id>")
def delete_measurement(measurement_id):
    measurement = measurement_service.get_measurement(measurement_id)
    payload = measurement_service.delete_measurement(measurement)
    return {"id": payload["id"], "deleted": True}


@bp.get("/entry-context")
def entry_context():
    """Options needed by the entry form in a single round trip.

    登录后返回的监测点/因子清单已按当前岗位生效口径收窄, 供前端渲染;
    真正的权限判定仍以提交接口为准。
    """
    user = access_service.current_user()
    all_stations = station_service.option_list()
    scope = access_service.effective_scope(user) if user else None

    from ..domain.standards import POLLUTANTS

    if scope is None:
        stations, pollutants = [], []
    else:
        if scope.all_stations:
            stations = all_stations
        else:
            allowed_ids = set(scope.station_ids())
            stations = [item for item in all_stations if item["id"] in allowed_ids]
        if scope.all_pollutants:
            pollutant_codes = list(POLLUTANTS.keys())
        else:
            pollutant_codes = [code for code in POLLUTANTS if code in set(scope.pollutants)]
        pollutants = [POLLUTANTS[code] for code in pollutant_codes]

    from ..models import User

    recorders = [
        {"id": row.id, "name": row.name, "username": row.username,
         "position_name": row.position.name if row.position else None}
        for row in User.query.filter_by(is_active=True).order_by(User.id.asc()).all()
    ]

    return {
        "current_user": user.to_dict(include_scope=True) if user else None,
        "stations": stations,
        "pollutants": pollutants,
        "all_station_count": len(all_stations),
        "periods": [{"value": key, "label": label} for key, label in PERIOD_LABELS.items()],
        "data_sources": [
            {"value": "manual", "label": DATA_SOURCE_LABELS["manual"]}
        ],
        "recorders": recorders,
    }

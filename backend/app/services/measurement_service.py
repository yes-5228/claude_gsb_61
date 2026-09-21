"""监测数据录入业务逻辑 (含超标自动判定 + 岗位录入范围授权)."""
from datetime import datetime

from ..domain import exceedance_rules
from ..domain.standards import get_pollutant
from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Exceedance, Measurement, Station
from . import auth_service


def get_measurement(measurement_id):
    measurement = db.session.get(Measurement, measurement_id)
    if measurement is None:
        raise NotFoundError("监测数据不存在: id=%s" % measurement_id)
    return measurement


def preview_entries(period, entries, operator=None, station_id=None):
    """Dry-run evaluation for the entry form (no database writes).

    当提供登录人 ``operator`` 与 ``station_id`` 时, 一并按岗位范围预检,
    使前端预览与最终提交的越权结论一致。
    """
    station = None
    if operator is not None and station_id:
        station = _load_station(station_id)
    results = []
    codes = []
    labels = {}
    for entry in entries:
        pollutant = str(entry.get("pollutant", "")).upper()
        meta = get_pollutant(pollutant)
        if meta is None:
            raise ValidationError("未知监测因子: %s" % entry.get("pollutant"), fields={"pollutant": "unknown"})
        try:
            value = float(entry.get("value"))
        except (TypeError, ValueError):
            raise ValidationError(
                "%s 监测值必须为数字" % meta["label"], fields={pollutant: "invalid_number"}
            )
        codes.append(pollutant)
        labels[pollutant] = meta["label"]
        evaluation = exceedance_rules.evaluate(pollutant, period, value)
        results.append(
            {
                "pollutant": pollutant,
                "pollutant_label": meta["label"],
                "value": value,
                "unit": meta["unit"],
                **evaluation,
            }
        )
    if operator is not None and station is not None:
        auth_service.assert_can_record(operator, station, codes, labels)
    return {"period": period, "results": results, "summary": exceedance_rules.summarize(results)}


def _load_station(station_id):
    station = db.session.get(Station, station_id)
    if station is None:
        raise NotFoundError("监测点不存在: id=%s" % station_id)
    return station


def record_entries(station_id, measured_at, period, entries, operator,
                   on_behalf_of_id=None, remark=None, overwrite=False,
                   data_source="manual"):
    """Persist one measured_at snapshot for a station.

    Duplicate (station, pollutant, period, measured_at) rows are reported back;
    when ``overwrite`` is true the existing row is refreshed instead.

    授权与归属:
      - ``operator`` 为已登录实际提交人; 点位/因子范围按其岗位"当前生效版本"校验,
        未通过直接抛 403 (绕过页面直连接口同样拦截)。
      - 录入人(recorder)归属被代录人或本人; 代录另记实际操作人 operator。
      - 录入人、提交时间、数据来源由服务端自动带出, 不信任请求体。
      - 记录登记当时的岗位范围版本快照, 范围调整不改变历史归属。
    """
    station = _load_station(station_id)
    if not entries:
        raise ValidationError("至少需要录入一条监测数据", fields={"entries": "empty"})

    recorder_user = auth_service.resolve_proxy_target(operator, on_behalf_of_id)
    is_proxy = recorder_user.id != operator.id

    # 先规范化全部条目, 再统一做一次范围校验 (点位 + 因子)
    normalized, seen, labels = [], set(), {}
    for entry in entries:
        pollutant = str(entry.get("pollutant", "")).upper()
        meta = get_pollutant(pollutant)
        if meta is None:
            raise ValidationError(
                "未知监测因子: %s" % entry.get("pollutant"), fields={"pollutant": "unknown"}
            )
        if pollutant in seen:
            raise ValidationError(
                "%s 在同一时刻重复提交" % meta["label"], fields={pollutant: "duplicated_in_batch"}
            )
        seen.add(pollutant)
        try:
            value = float(entry.get("value"))
        except (TypeError, ValueError):
            raise ValidationError(
                "%s 监测值必须为数字" % meta["label"], fields={pollutant: "invalid_number"}
            )
        normalized.append((pollutant, meta, value))
        labels[pollutant] = meta["label"]

    scope, scope_position_id = auth_service.assert_can_record(
        operator, station, [item[0] for item in normalized], labels
    )

    existing = {
        row.pollutant: row
        for row in Measurement.query.filter_by(
            station_id=station.id, period=period, measured_at=measured_at
        ).all()
    }

    now = datetime.now()
    created, updated, exceeded, duplicates, evaluated = [], [], [], [], []
    for pollutant, meta, value in normalized:
        evaluation = exceedance_rules.evaluate(pollutant, period, value)
        evaluated.append(
            {
                "pollutant": pollutant,
                "pollutant_label": meta["label"],
                "value": value,
                "unit": meta["unit"],
                **evaluation,
            }
        )

        record = existing.get(pollutant)
        if record is not None and not overwrite:
            duplicates.append(
                {
                    "pollutant": pollutant,
                    "pollutant_label": meta["label"],
                    "value": value,
                    "existing_id": record.id,
                    "message": "该时刻 %s 数据已存在" % meta["label"],
                }
            )
            continue

        is_new = record is None
        if is_new:
            record = Measurement(station_id=station.id, pollutant=pollutant, period=period,
                                 measured_at=measured_at)
            db.session.add(record)

        record.value = value
        record.unit = meta["unit"]
        record.limit_value = evaluation["limit"]
        record.exceed_ratio = evaluation["ratio"]
        record.is_exceeded = evaluation["exceeded"]
        # 以下字段服务端自动带出, 忽略任何前端传值
        record.data_source = data_source
        record.recorder_id = recorder_user.id
        record.recorder = recorder_user.display_name
        record.operator_id = operator.id
        record.operator_name = operator.display_name
        record.is_proxy = is_proxy
        record.submitted_at = now
        record.scope_version_id = scope.id if scope is not None else None
        record.scope_position_id = scope_position_id
        record.remark = remark

        _sync_exceedance(record, meta, evaluation)
        db.session.flush()
        (created if is_new else updated).append(record.to_dict(include_station=True))
        if evaluation["exceeded"]:
            exceeded.append(record.exceedance.to_dict() if record.exceedance else None)

    if not created and not updated and duplicates:
        raise ConflictError(
            "所选时刻已存在相同数据, 如需覆盖请勾选\"覆盖已有数据\": %s"
            % ", ".join(item["pollutant_label"] for item in duplicates)
        )

    db.session.commit()
    return {
        "station": station.to_option(),
        "measured_at": measured_at.isoformat(timespec="seconds"),
        "period": period,
        "created": created,
        "updated": updated,
        "exceedances": [item for item in exceeded if item],
        "duplicates": duplicates,
        "evaluations": evaluated,
        "submission": {
            "recorder_id": recorder_user.id,
            "recorder": recorder_user.display_name,
            "operator_id": operator.id,
            "operator": operator.display_name,
            "is_proxy": is_proxy,
            "submitted_at": now.isoformat(timespec="seconds"),
            "data_source": data_source,
            "scope_version_id": scope.id if scope is not None else None,
        },
        "summary": {
            "created_count": len(created),
            "updated_count": len(updated),
            "exceeded_count": len([item for item in evaluated if item["exceeded"]]),
            "duplicate_count": len(duplicates),
        },
    }


def _sync_exceedance(record, meta, evaluation):
    """Create / refresh / drop the exceedance row attached to a measurement."""
    if evaluation["exceeded"]:
        if record.exceedance is None:
            record.exceedance = Exceedance(
                station_id=record.station_id,
                pollutant=record.pollutant,
                period=record.period,
                measured_at=record.measured_at,
                value=record.value,
                limit_value=evaluation["limit"],
                exceed_ratio=evaluation["ratio"],
                level=evaluation["level"],
                status="pending",
            )
        else:
            record.exceedance.value = record.value
            record.exceedance.limit_value = evaluation["limit"]
            record.exceedance.exceed_ratio = evaluation["ratio"]
            record.exceedance.level = evaluation["level"]
            record.exceedance.measured_at = record.measured_at
    elif record.exceedance is not None:
        db.session.delete(record.exceedance)


def delete_measurement(measurement):
    payload = measurement.to_dict()
    db.session.delete(measurement)
    db.session.commit()
    return payload

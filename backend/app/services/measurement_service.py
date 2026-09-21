"""监测数据录入业务逻辑 (含超标自动判定)."""
from datetime import datetime

from ..domain import exceedance_rules
from ..domain.standards import get_pollutant
from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Exceedance, Measurement, Station
from . import access_service


def get_measurement(measurement_id):
    measurement = db.session.get(Measurement, measurement_id)
    if measurement is None:
        raise NotFoundError("监测数据不存在: id=%s" % measurement_id)
    return measurement


def preview_entries(period, entries):
    """Dry-run evaluation for the entry form (no database writes)."""
    results = []
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
    return {"period": period, "results": results, "summary": exceedance_rules.summarize(results)}


def _load_station(station_id):
    station = db.session.get(Station, station_id)
    if station is None:
        raise NotFoundError("监测点不存在: id=%s" % station_id)
    return station


def record_entries(station_id, measured_at, period, entries, data_source="manual",
                   recorder=None, remark=None, overwrite=False, actor=None,
                   recorder_user=None, enforce_scope=True, submitted_at=None):
    """Persist one measured_at snapshot for a station.

    Duplicate (station, pollutant, period, measured_at) rows are reported back;
    when ``overwrite`` is true the existing row is refreshed instead.

    权限与审计:
    - ``actor`` 为实际提交的登录用户, 服务端实时按其岗位当前生效口径校验点位与因子,
      绕过页面直接提交同样在此被拦截 (``enforce_scope=False`` 仅供系统/种子数据使用);
    - 提交人 (operator)、提交时间 (submitted_at)、数据来源 (data_source) 均由服务端
      写入, 不信任请求体;
    - ``recorder_user`` 为名义录入人, 与提交人不一致时自动标记代录 ``is_proxy=True``;
    - 新建记录时快照当时岗位与口径版本, 后续范围调整不改变历史归属; 覆盖更新也保留
      首次录入时的归属信息。
    """
    station = _load_station(station_id)
    if not entries:
        raise ValidationError("至少需要录入一条监测数据", fields={"entries": "empty"})

    # 先把因子/数值规范化, 再用规范后的因子清单做权限校验, 保证越权提示能给出因子名
    normalized = []
    seen = set()
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
        normalized.append((entry, pollutant, meta, value))

    scope = None
    if enforce_scope:
        if actor is None:
            from ..errors import AuthenticationError

            raise AuthenticationError()
        scope = access_service.authorize_entry(
            actor,
            station.id,
            [item[1] for item in normalized],
            station_name=station.name,
            pollutant_labels={item[1]: item[2]["label"] for item in normalized},
        )

    # 名义录入人: 显式选择优先, 否则为提交人本人; 代录以登录账号真实身份为准
    recorder_name = recorder
    recorder_id = None
    if recorder_user is not None:
        recorder_name = recorder_user.name
        recorder_id = recorder_user.id
    elif actor is not None:
        recorder_name = actor.name
        recorder_id = actor.id
    is_proxy = bool(actor and recorder_id and actor.id != recorder_id)
    moment = submitted_at or datetime.now()

    existing = {
        row.pollutant: row
        for row in Measurement.query.filter_by(
            station_id=station.id, period=period, measured_at=measured_at
        ).all()
    }

    created, updated, exceeded, duplicates, evaluated = [], [], [], [], []
    for entry, pollutant, meta, value in normalized:
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
        # 数据来源由服务端决定: 页面录入一律为手工录入, 设备/导入由系统通道写入
        record.data_source = data_source
        record.remark = entry.get("remark") or remark

        if is_new:
            # 审计与口径归属仅在首次写入时落定, 覆盖更新保持原归属不变
            record.operator_id = actor.id if actor else None
            record.operator_name = actor.name if actor else recorder_name
            record.recorder_id = recorder_id
            record.recorder = recorder_name
            record.is_proxy = is_proxy
            record.submitted_at = moment
            record.position_id = actor.position_id if actor else None
            record.scope_id = scope.id if scope else None
        elif overwrite:
            # 覆盖更新: 记录“最后修改人”, 但保留首次录入的归属与口径快照
            record.operator_id = actor.id if actor else record.operator_id
            record.operator_name = actor.name if actor else record.operator_name
            record.is_proxy = is_proxy

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
        "submitted_by": {"operator_id": actor.id if actor else None,
                         "operator_name": actor.name if actor else recorder_name,
                         "recorder_id": recorder_id,
                         "recorder_name": recorder_name,
                         "is_proxy": is_proxy,
                         "submitted_at": moment.isoformat(timespec="seconds")},
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

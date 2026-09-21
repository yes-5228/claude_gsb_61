"""监测数据记录."""
from ..domain.constants import DATA_SOURCE_LABELS, PERIOD_LABELS, label_of
from ..domain.standards import get_pollutant
from ..extensions import db
from .base import TimestampMixin, iso


class Measurement(TimestampMixin, db.Model):
    __tablename__ = "measurements"
    __table_args__ = (
        db.UniqueConstraint(
            "station_id", "pollutant", "period", "measured_at",
            name="uq_measurement_point_factor_time",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(
        db.Integer, db.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pollutant = db.Column(db.String(16), nullable=False, index=True)
    period = db.Column(db.String(16), nullable=False, default="hourly")
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(16))
    limit_value = db.Column(db.Float)
    exceed_ratio = db.Column(db.Float)
    is_exceeded = db.Column(db.Boolean, nullable=False, default=False, index=True)
    measured_at = db.Column(db.DateTime, nullable=False, index=True)
    data_source = db.Column(db.String(16), nullable=False, default="manual")
    # recorder_*: 数据归属的录入人; 代录时归属被代录人, operator_* 记实际操作人
    recorder_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    recorder = db.Column(db.String(64))
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    operator_name = db.Column(db.String(64))
    is_proxy = db.Column(db.Boolean, nullable=False, default=False)
    submitted_at = db.Column(db.DateTime, nullable=True)
    # 登记当时生效的岗位范围口径快照, 范围调整后历史归属不变
    scope_version_id = db.Column(
        db.Integer, db.ForeignKey("position_scope_versions.id"), nullable=True
    )
    scope_position_id = db.Column(db.Integer, nullable=True, index=True)
    remark = db.Column(db.Text)

    station = db.relationship("Station", back_populates="measurements")
    exceedance = db.relationship(
        "Exceedance",
        back_populates="measurement",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def pollutant_label(self):
        meta = get_pollutant(self.pollutant)
        return meta["label"] if meta else self.pollutant

    def to_dict(self, include_station=False):
        payload = {
            "id": self.id,
            "station_id": self.station_id,
            "pollutant": self.pollutant,
            "pollutant_label": self.pollutant_label(),
            "period": self.period,
            "period_label": label_of(PERIOD_LABELS, self.period),
            "value": self.value,
            "unit": self.unit,
            "limit_value": self.limit_value,
            "exceed_ratio": self.exceed_ratio,
            "is_exceeded": bool(self.is_exceeded),
            "measured_at": iso(self.measured_at),
            "data_source": self.data_source,
            "data_source_label": label_of(DATA_SOURCE_LABELS, self.data_source),
            "recorder_id": self.recorder_id,
            "recorder": self.recorder,
            "operator_id": self.operator_id,
            "operator_name": self.operator_name,
            "is_proxy": bool(self.is_proxy),
            "submitted_at": iso(self.submitted_at) if self.submitted_at else iso(self.created_at),
            "scope_version_id": self.scope_version_id,
            "scope_position_id": self.scope_position_id,
            "remark": self.remark,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
            "exceedance_id": self.exceedance.id if self.exceedance else None,
            "exceedance_status": self.exceedance.status if self.exceedance else None,
        }
        if include_station and self.station:
            payload["station"] = {
                "id": self.station.id,
                "code": self.station.code,
                "name": self.station.name,
                "area": self.station.area,
                "station_type_label": self.station.to_dict()["station_type_label"],
            }
        return payload

    def __repr__(self):
        return "<Measurement %s %s %s>" % (self.station_id, self.pollutant, self.measured_at)

    @classmethod
    def unique_key(cls, station_id, pollutant, period, measured_at):
        return "%s|%s|%s|%s" % (station_id, pollutant, period, iso(measured_at))

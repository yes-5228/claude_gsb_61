"""岗位与录入权限口径.

一个岗位可以拥有多版“录入范围口径”, 每版带 ``effective_from`` 生效时间:
- 提交录入时按“提交时刻”取该岗位已生效的最新一版进行鉴权;
- 调整范围时登记新生效版本, 只影响生效时间之后的录入;
- 历史监测数据在写入时快照当时的岗位与口径版本, 归属永不随后续调整改变。
"""
from datetime import datetime

from ..extensions import db
from .base import TimestampMixin, iso

# 岗位口径版本 <-> 可录入监测点 的关联表 (因子使用 ScopePollutant 映射类)
scope_station = db.Table(
    "scope_stations",
    db.Column("scope_id", db.Integer, db.ForeignKey("position_scopes.id", ondelete="CASCADE"),
              primary_key=True),
    db.Column("station_id", db.Integer, db.ForeignKey("stations.id", ondelete="CASCADE"),
              primary_key=True),
)


class Position(TimestampMixin, db.Model):
    """岗位 (如: 福田区录入员、设备运维管理员)."""

    __tablename__ = "positions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    users = db.relationship("User", back_populates="position")
    scopes = db.relationship(
        "PositionScope",
        back_populates="position",
        cascade="all, delete-orphan",
        order_by="PositionScope.effective_from.desc()",
    )

    def current_scope(self, at=None):
        """返回 ``at`` 时刻已生效的最新一版口径; 从未配置过则返回 None。"""
        moment = at or datetime.now()
        return (
            PositionScope.query.filter(
                PositionScope.position_id == self.id,
                PositionScope.effective_from <= moment,
            )
            .order_by(PositionScope.effective_from.desc())
            .first()
        )

    def to_dict(self, include_scopes=False):
        payload = {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "is_active": bool(self.is_active),
        }
        if include_scopes:
            payload["scopes"] = [scope.to_dict() for scope in self.scopes]
        return payload

    def __repr__(self):
        return "<Position %s>" % self.code


class PositionScope(TimestampMixin, db.Model):
    """岗位录入范围的一版口径, 自 ``effective_from`` 起生效。"""

    __tablename__ = "position_scopes"
    __table_args__ = (
        db.UniqueConstraint(
            "position_id", "effective_from", name="uq_scope_position_effective_from"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(
        db.Integer, db.ForeignKey("positions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    effective_from = db.Column(db.DateTime, nullable=False, index=True)
    all_stations = db.Column(db.Boolean, nullable=False, default=False)
    all_pollutants = db.Column(db.Boolean, nullable=False, default=False)
    remark = db.Column(db.String(255))

    position = db.relationship("Position", back_populates="scopes")
    stations = db.relationship("Station", secondary=scope_station)
    pollutant_codes = db.relationship("ScopePollutant", cascade="all, delete-orphan",
                                      passive_deletes=True)

    @property
    def pollutants(self):
        return [item.pollutant for item in self.pollutant_codes]

    def station_ids(self):
        if self.all_stations:
            from .station import Station

            return [row.id for row in Station.query.with_entities(Station.id).all()]
        return [row.id for row in self.stations]

    def to_dict(self):
        return {
            "id": self.id,
            "position_id": self.position_id,
            "effective_from": iso(self.effective_from),
            "all_stations": bool(self.all_stations),
            "all_pollutants": bool(self.all_pollutants),
            "station_ids": self.station_ids(),
            "pollutants": self.pollutants,
            "remark": self.remark,
            "created_at": iso(self.created_at),
        }

    def __repr__(self):
        return "<PositionScope position=%s from=%s>" % (self.position_id, self.effective_from)


class ScopePollutant(db.Model):
    """口径版本允许录入的因子 (与 scope_pollutant 关联表对应, 便于 ORM 级联)."""

    __tablename__ = "scope_pollutants"

    scope_id = db.Column(
        db.Integer, db.ForeignKey("position_scopes.id", ondelete="CASCADE"), primary_key=True
    )
    pollutant = db.Column(db.String(16), primary_key=True)

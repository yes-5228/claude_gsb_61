"""岗位与用户 (登录账号).

岗位决定"可录入哪些监测点 / 哪些因子"; 用户归属于一个岗位,
停用或调岗后其可录入范围立即随岗位口径变化, 无需逐条改授权。
"""
import hashlib
import hmac
import os
from datetime import datetime

from ..extensions import db
from .base import TimestampMixin, iso

# 演示/初始化默认口令; 生产可通过 CLI 重置
DEFAULT_PASSWORD = "air123456"

_PBKDF2_ROUNDS = 120_000


def hash_password(password, salt=None):
    """Return ``salt$digest`` using PBKDF2-HMAC-SHA256 (no extra dependency)."""
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", str(password).encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS
    ).hex()
    return "%s$%s" % (salt, digest)


def verify_password(password, stored):
    try:
        salt, digest = str(stored).split("$", 1)
    except (AttributeError, ValueError):
        return False
    candidate = hash_password(password, salt=salt)
    return hmac.compare_digest(candidate, str(stored))


class Position(TimestampMixin, db.Model):
    """岗位: 绑定一组"带生效时间"的范围版本。"""

    __tablename__ = "positions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    can_proxy = db.Column(db.Boolean, nullable=False, default=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    remark = db.Column(db.String(255))

    scope_versions = db.relationship(
        "PositionScopeVersion",
        back_populates="position",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PositionScopeVersion.effective_from.desc()",
    )
    users = db.relationship("User", back_populates="position")

    def current_scope(self, at=None):
        """取在 ``at`` 时刻已生效的最新一版范围; 无任何版本返回 None。"""
        at = at or datetime.now()
        return (
            PositionScopeVersion.query.filter(
                PositionScopeVersion.position_id == self.id,
                PositionScopeVersion.effective_from <= at,
            )
            .order_by(PositionScopeVersion.effective_from.desc(), PositionScopeVersion.id.desc())
            .first()
        )

    def describe_scope(self, at=None):
        scope = None if self.is_admin else self.current_scope(at)
        if self.is_admin or scope is None:
            return {"stations": [], "pollutants": [], "all_stations": True, "all_pollutants": True}
        return {
            "stations": scope.station_codes,
            "pollutants": scope.pollutant_codes,
            "all_stations": scope.all_stations,
            "all_pollutants": scope.all_pollutants,
        }

    def to_dict(self, include_scope=False, at=None):
        payload = {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "can_proxy": bool(self.can_proxy),
            "is_admin": bool(self.is_admin),
            "active": bool(self.active),
            "remark": self.remark,
            "user_count": len(self.users),
        }
        if include_scope:
            scope = None if self.is_admin else self.current_scope(at)
            payload["current_scope"] = None if scope is None else scope.to_dict()
            payload["scope_versions"] = [item.to_dict() for item in self.scope_versions]
        return payload


class PositionScopeVersion(TimestampMixin, db.Model):
    """岗位可录入范围的一个版本, 按生效时间挂接。

    - ``effective_from`` 之后的录入按本版校验; 之前已登记数据的归属口径不变。
    - 空集合 + ``all_*`` 表示"全部", 便于对新点位/新因子自动放开或收紧。
    """

    __tablename__ = "position_scope_versions"

    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(
        db.Integer, db.ForeignKey("positions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    effective_from = db.Column(db.DateTime, nullable=False)
    all_stations = db.Column(db.Boolean, nullable=False, default=True)
    all_pollutants = db.Column(db.Boolean, nullable=False, default=True)
    # 以逗号分隔的点位编码 / 因子编码快照, 避免点位删除导致版本被级联破坏
    station_codes_text = db.Column(db.Text, nullable=False, default="")
    pollutant_codes_text = db.Column(db.Text, nullable=False, default="")
    remark = db.Column(db.String(255))

    position = db.relationship("Position", back_populates="scope_versions")

    @property
    def station_codes(self):
        return [item for item in self.station_codes_text.split(",") if item]

    @station_codes.setter
    def station_codes(self, codes):
        self.station_codes_text = ",".join(sorted({str(c).strip() for c in codes if str(c).strip()}))

    @property
    def pollutant_codes(self):
        return [item for item in self.pollutant_codes_text.split(",") if item]

    @pollutant_codes.setter
    def pollutant_codes(self, codes):
        self.pollutant_codes_text = ",".join(sorted({str(c).strip().upper() for c in codes if str(c).strip()}))

    def to_dict(self):
        return {
            "id": self.id,
            "position_id": self.position_id,
            "effective_from": iso(self.effective_from),
            "all_stations": bool(self.all_stations),
            "all_pollutants": bool(self.all_pollutants),
            "station_codes": self.station_codes,
            "pollutant_codes": self.pollutant_codes,
            "remark": self.remark,
        }


class User(TimestampMixin, db.Model):
    """登录账号; display_name 即带出的录入人姓名。"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False)
    display_name = db.Column(db.String(64), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    position_id = db.Column(
        db.Integer, db.ForeignKey("positions.id"), nullable=False, index=True
    )
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    last_login_at = db.Column(db.DateTime)
    remark = db.Column(db.String(255))

    position = db.relationship("Position", back_populates="users")

    def set_password(self, password):
        self.password_hash = hash_password(password)

    def check_password(self, password):
        return verify_password(password, self.password_hash)

    def can_record(self):
        """账号启用且岗位启用才允许录入 (停用/调岗立即生效)。"""
        return bool(self.active and self.position and self.position.active)

    def scope_at(self, at=None):
        """返回该用户当前生效的录入范围; 管理员为全量。"""
        if self.position and self.position.is_admin:
            return {"all_stations": True, "all_pollutants": True,
                    "station_codes": [], "pollutant_codes": []}
        scope = self.position.current_scope(at) if self.position else None
        if scope is None:  # 未配置任何范围版本 => 没有任何点位/因子可录
            return {"all_stations": False, "all_pollutants": False,
                    "station_codes": [], "pollutant_codes": []}
        return {
            "all_stations": bool(scope.all_stations),
            "all_pollutants": bool(scope.all_pollutants),
            "station_codes": scope.station_codes,
            "pollutant_codes": scope.pollutant_codes,
        }

    def to_dict(self, include_scope=False):
        payload = {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "position_id": self.position_id,
            "position_name": self.position.name if self.position else None,
            "is_admin": bool(self.position and self.position.is_admin),
            "can_proxy": bool(self.position and self.position.can_proxy),
            "active": bool(self.active),
            "last_login_at": iso(self.last_login_at),
            "remark": self.remark,
        }
        if include_scope:
            payload["scope"] = self.scope_at()
        return payload

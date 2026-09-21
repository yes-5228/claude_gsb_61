"""系统操作人员 (录入账号).

演示环境采用“令牌令牌头 X-Operator-Token”做轻量身份切换;
每次录入都实时查询账号状态与所属岗位, 停用或调岗后可录入范围立即收紧。
"""
import secrets

from ..extensions import db
from .base import TimestampMixin, iso


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    position_id = db.Column(
        db.Integer, db.ForeignKey("positions.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    position = db.relationship("Position", back_populates="users")

    @staticmethod
    def generate_token():
        return secrets.token_hex(16)

    def entry_scope(self, at=None):
        """当前时刻生效的录入口径 (账号/岗位停用均视为无口径)。"""
        if not self.is_active or self.position is None or not self.position.is_active:
            return None
        return self.position.current_scope(at=at)

    def to_dict(self, include_scope=False, at=None):
        payload = {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "is_active": bool(self.is_active),
            "is_admin": bool(self.is_admin),
            "position_id": self.position_id,
            "position_name": self.position.name if self.position else None,
        }
        if include_scope:
            scope = self.entry_scope(at=at)
            payload["scope"] = scope.to_dict() if scope else None
        return payload

    def __repr__(self):
        return "<User %s>" % self.username

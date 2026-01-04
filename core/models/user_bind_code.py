from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint

from .base import Base, Column


class UserBindCode(Base):
    __tablename__ = "user_bind_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(String(255), index=True, nullable=False)
    code = Column(String(32), index=True, nullable=False)
    purpose = Column(String(50), default="wechat_follow_bind")

    # 0: pending, 1: used, 9: expired/invalidated
    status = Column(Integer, default=0)

    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)
    used_openid = Column(String(255))

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("code", name="uq_user_bind_codes_code"),)


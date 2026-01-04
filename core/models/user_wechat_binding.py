from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint

from .base import Base, Column


class UserWechatBinding(Base):
    __tablename__ = "user_wechat_bindings"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(String(255), index=True, nullable=False)
    # Identifier provided by your robot / WeChat integration layer.
    # (Could be openid/unionid/uid — store as a string.)
    wechat_openid = Column(String(255), index=True, nullable=False)
    wechat_unionid = Column(String(255), index=True, nullable=True)

    # 1: active, 0: inactive
    is_active = Column(Integer, default=1)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_wechat_bindings_user"),
        UniqueConstraint("wechat_openid", name="uq_user_wechat_bindings_openid"),
    )


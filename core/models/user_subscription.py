from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint

from .base import Base, Column


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(String(255), index=True, nullable=False)
    feed_id = Column(String(255), index=True, nullable=False)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("user_id", "feed_id", name="uq_user_subscriptions_user_feed"),)


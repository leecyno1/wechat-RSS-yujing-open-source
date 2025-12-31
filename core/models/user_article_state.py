from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint

from .base import Base, Column


class UserArticleState(Base):
    __tablename__ = "user_article_states"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(String(255), index=True, nullable=False)
    article_id = Column(String(255), index=True, nullable=False)

    # 0: unread, 1: read
    is_read = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("user_id", "article_id", name="uq_user_article_states_user_article"),)


from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint

from .base import Base, Column


class FavoriteCategory(Base):
    __tablename__ = "favorite_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(String(255), index=True, nullable=False)
    name = Column(String(128), nullable=False)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_favorite_categories_user_name"),)


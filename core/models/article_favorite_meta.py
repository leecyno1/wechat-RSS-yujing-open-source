from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint

from .base import Base, Column, Text


class ArticleFavoriteMeta(Base):
    __tablename__ = "article_favorite_meta"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(String(255), index=True, nullable=False)
    article_id = Column(String(255), index=True, nullable=False)

    # User-defined category for this favorite article.
    category = Column(String(128), nullable=True)
    # JSON array string for custom tags.
    tags_json = Column(Text, nullable=True)
    # Open count tracked on client interactions; used for ranking and recommendations.
    open_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    __table_args__ = (UniqueConstraint("user_id", "article_id", name="uq_article_favorite_meta_user_article"),)


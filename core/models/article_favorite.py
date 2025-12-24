from .base import Base, Column, String, Integer, DateTime


class ArticleFavorite(Base):
    __tablename__ = "article_favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), index=True, nullable=False)
    article_id = Column(String(255), index=True, nullable=False)

    created_at = Column(DateTime)


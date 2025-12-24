from .base import Base, Column, String, Integer, DateTime, Text


class ArticleNote(Base):
    __tablename__ = "article_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), index=True, nullable=False)
    article_id = Column(String(255), index=True, nullable=False)

    content = Column(Text, nullable=False)

    created_at = Column(DateTime)
    updated_at = Column(DateTime)


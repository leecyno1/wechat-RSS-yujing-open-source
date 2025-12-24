from .base import Base, Column, String, Integer, DateTime, Text


class ArticleInsight(Base):
    __tablename__ = "article_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(String(255), unique=True, index=True, nullable=False)

    summary = Column(Text)
    headings_json = Column(Text)  # JSON string: [{level: 1|2, text: "..."}]

    # JSON string: {"highlight": "...", "points": ["...", ...]}
    key_points_json = Column(Text)

    llm_breakdown_json = Column(Text)  # JSON string: full breakdown (1-3 levels)
    llm_provider = Column(String(50))
    llm_model = Column(String(255))

    content_hash = Column(String(64), index=True)
    status = Column(Integer, default=0)  # 0: none, 1: basic_ok, 2: llm_ok, 9: failed
    error = Column(Text)

    created_at = Column(DateTime)
    updated_at = Column(DateTime)

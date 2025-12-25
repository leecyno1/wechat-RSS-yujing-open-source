from __future__ import annotations

from dataclasses import asdict, dataclass

from core.db import DB
from core.models import Article, DATA_STATUS, Feed


@dataclass
class ArticleInfo:
    no_content_count: int = 0
    has_content_count: int = 0
    all_count: int = 0
    wrong_count: int = 0
    mp_all_count: int = 0
    error: str = ""


def laxArticle() -> dict:
    """Return lightweight article stats.

    IMPORTANT: Do not touch DB at import-time; this must be called lazily.
    """
    info = ArticleInfo()
    try:
        session = DB.get_session()
        info.no_content_count = session.query(Article).filter(Article.content.is_(None)).count()
        info.all_count = session.query(Article).count()
        info.has_content_count = max(0, int(info.all_count) - int(info.no_content_count))
        info.wrong_count = session.query(Article).filter(Article.status != DATA_STATUS.ACTIVE).count()
        info.mp_all_count = session.query(Feed).distinct(Feed.id).count()
    except Exception as e:
        info.error = str(e)
    return asdict(info)

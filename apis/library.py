import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func

from apis.base import format_search_kw, success_response
from core.auth import get_current_user
from core.db import DB
from core.models.article import Article, ArticleBase
from core.models.article_favorite import ArticleFavorite
from core.models.article_insight import ArticleInsight
from core.models.article_note import ArticleNote
from core.models.feed import Feed


router = APIRouter(prefix="/library", tags=["数据接口"])


def _get_user_id(current_user: dict) -> str:
    u = current_user.get("original_user")
    return str(getattr(u, "id", "")) or current_user.get("username", "")


@router.get("/articles", summary="文章库列表(可包含洞察/收藏/笔记统计)")
async def list_library_articles(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    mp_id: str | None = Query(None),
    search: str | None = Query(None),
    include_content: bool = Query(False),
    include_insights: bool = Query(True),
    only_favorited: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)

    Art = Article if include_content else ArticleBase
    q = session.query(Art, Feed).join(Feed, Feed.id == Art.mp_id)

    if mp_id:
        q = q.filter(Art.mp_id == mp_id)
    if search:
        q = q.filter(format_search_kw(search))

    if only_favorited:
        q = q.join(
            ArticleFavorite,
            (ArticleFavorite.article_id == Art.id) & (ArticleFavorite.user_id == user_id),
        )

    total = q.count()
    rows = q.order_by(Art.publish_time.desc()).offset(offset).limit(limit).all()

    article_ids = [a.id for a, _f in rows]

    insights_map = {}
    if include_insights and article_ids:
        for ins in session.query(ArticleInsight).filter(ArticleInsight.article_id.in_(article_ids)).all():
            insights_map[ins.article_id] = ins

    fav_set = set()
    if article_ids:
        for (aid,) in (
            session.query(ArticleFavorite.article_id)
            .filter(ArticleFavorite.user_id == user_id, ArticleFavorite.article_id.in_(article_ids))
            .all()
        ):
            fav_set.add(aid)

    notes_count = {}
    if article_ids:
        for aid, cnt in (
            session.query(ArticleNote.article_id, func.count(ArticleNote.id))
            .filter(ArticleNote.user_id == user_id, ArticleNote.article_id.in_(article_ids))
            .group_by(ArticleNote.article_id)
            .all()
        ):
            notes_count[aid] = int(cnt)

    items = []
    for art, feed in rows:
        d = art.__dict__.copy()
        d.pop("_sa_instance_state", None)
        d["feed"] = {
            "id": feed.id,
            "name": feed.mp_name,
            "cover": feed.mp_cover,
            "intro": feed.mp_intro,
        }
        d["favorited"] = art.id in fav_set
        d["notes_count"] = notes_count.get(art.id, 0)
        if include_insights:
            ins = insights_map.get(art.id)
            if ins:
                d["insights"] = {
                    "summary": ins.summary or "",
                    "headings": json.loads(ins.headings_json) if ins.headings_json else [],
                    "status": ins.status,
                }
            else:
                d["insights"] = None
        items.append(d)

    return success_response({"list": items, "total": total})


@router.get("/articles/{article_id}", summary="文章库详情(含洞察/收藏/笔记)")
async def get_library_article(
    article_id: str,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)

    row = (
        session.query(Article, Feed)
        .join(Feed, Feed.id == Article.mp_id)
        .filter(Article.id == article_id)
        .first()
    )
    if not row:
        return success_response(None)
    art, feed = row

    ins = session.query(ArticleInsight).filter(ArticleInsight.article_id == article_id).first()
    fav = (
        session.query(ArticleFavorite.id)
        .filter(ArticleFavorite.user_id == user_id, ArticleFavorite.article_id == article_id)
        .first()
    )
    notes = (
        session.query(ArticleNote)
        .filter(ArticleNote.user_id == user_id, ArticleNote.article_id == article_id)
        .order_by(ArticleNote.updated_at.desc(), ArticleNote.id.desc())
        .limit(50)
        .all()
    )

    d = art.__dict__.copy()
    d.pop("_sa_instance_state", None)
    d["feed"] = {
        "id": feed.id,
        "name": feed.mp_name,
        "cover": feed.mp_cover,
        "intro": feed.mp_intro,
    }
    d["favorited"] = bool(fav)
    d["insights"] = (
        {
            "summary": ins.summary or "",
            "headings": json.loads(ins.headings_json) if ins and ins.headings_json else [],
            "llm_breakdown": json.loads(ins.llm_breakdown_json) if ins and ins.llm_breakdown_json else None,
            "status": ins.status if ins else 0,
            "error": ins.error if ins else "",
        }
        if ins
        else None
    )
    d["notes"] = [n.__dict__ | {"_sa_instance_state": None} for n in notes]
    for n in d["notes"]:
        n.pop("_sa_instance_state", None)
    return success_response(d)


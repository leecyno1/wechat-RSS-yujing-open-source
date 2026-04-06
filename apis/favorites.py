from datetime import datetime
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status as fast_status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func

from apis.base import error_response, success_response
from core.auth import get_current_user
from core.db import DB
from core.models.article import ArticleBase
from core.models.article_favorite import ArticleFavorite
from core.models.article_favorite_meta import ArticleFavoriteMeta
from core.models.base import DATA_STATUS
from core.models.favorite_category import FavoriteCategory
from core.models.feed import Feed


router = APIRouter(prefix="/favorites", tags=["收藏"])


def _get_user_id(current_user: dict) -> str:
    u = current_user.get("original_user")
    return str(getattr(u, "id", "")) or current_user.get("username", "")


def _normalize_tags(raw_tags: list[str] | None) -> list[str]:
    if not raw_tags:
        return []
    out: list[str] = []
    seen = set()
    for x in raw_tags:
        t = str(x or "").strip()
        if not t:
            continue
        t = t[:32]
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= 30:
            break
    return out


class FavoriteMetaUpsertIn(BaseModel):
    category: str | None = None
    tags: list[str] | None = None
    open_count_inc: int = Field(0, ge=0, le=1000)


class FavoriteCategoryIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


@router.post("/article/{article_id}", summary="收藏文章")
async def favorite_article(
    article_id: str,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)

    article = session.query(ArticleBase.id).filter(ArticleBase.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )

    exists = (
        session.query(ArticleFavorite)
        .filter(ArticleFavorite.user_id == user_id, ArticleFavorite.article_id == article_id)
        .first()
    )
    if exists:
        return success_response({"article_id": article_id, "favorited": True})

    fav = ArticleFavorite(user_id=user_id, article_id=article_id, created_at=datetime.now())
    session.add(fav)
    session.commit()
    return success_response({"article_id": article_id, "favorited": True})


@router.delete("/article/{article_id}", summary="取消收藏")
async def unfavorite_article(
    article_id: str,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)
    session.query(ArticleFavorite).filter(
        ArticleFavorite.user_id == user_id, ArticleFavorite.article_id == article_id
    ).delete(synchronize_session=False)
    session.query(ArticleFavoriteMeta).filter(
        ArticleFavoriteMeta.user_id == user_id, ArticleFavoriteMeta.article_id == article_id
    ).delete(synchronize_session=False)
    session.commit()
    return success_response({"article_id": article_id, "favorited": False})


@router.get("", summary="获取收藏列表")
async def list_favorites(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)

    q = (
        session.query(ArticleFavorite, ArticleBase)
        .join(ArticleBase, ArticleBase.id == ArticleFavorite.article_id)
        .filter(ArticleFavorite.user_id == user_id)
        .order_by(ArticleFavorite.created_at.desc())
    )
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    items = []
    for fav, art in rows:
        d = art.__dict__.copy()
        d.pop("_sa_instance_state", None)
        d["favorited_at"] = str(getattr(fav, "created_at", "") or "")
        items.append(d)
    return success_response({"list": items, "total": total})


@router.get("/meta", summary="获取收藏分类/标签元数据")
async def list_favorite_meta(
    only_favorited: bool = Query(True, description="仅返回当前收藏文章的元数据"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)

    q = session.query(ArticleFavoriteMeta).filter(ArticleFavoriteMeta.user_id == user_id)
    if only_favorited:
        q = q.join(
            ArticleFavorite,
            and_(
                ArticleFavorite.user_id == ArticleFavoriteMeta.user_id,
                ArticleFavorite.article_id == ArticleFavoriteMeta.article_id,
            ),
        )

    metas = q.all()
    out = []
    for m in metas:
        tags = []
        try:
            tags = json.loads(m.tags_json or "[]")
            if not isinstance(tags, list):
                tags = []
        except Exception:
            tags = []
        out.append(
            {
                "article_id": str(m.article_id),
                "category": str(m.category or ""),
                "tags": _normalize_tags(tags),
                "open_count": int(m.open_count or 0),
                "updated_at": str(getattr(m, "updated_at", "") or ""),
            }
        )

    cats = (
        session.query(FavoriteCategory)
        .filter(FavoriteCategory.user_id == user_id)
        .order_by(FavoriteCategory.name.asc())
        .all()
    )
    categories = [str(c.name or "").strip() for c in cats if str(c.name or "").strip()]
    return success_response({"list": out, "categories": categories})


@router.put("/meta/{article_id}", summary="更新收藏分类/标签元数据")
async def upsert_favorite_meta(
    article_id: str,
    payload: FavoriteMetaUpsertIn,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)

    article = session.query(ArticleBase.id).filter(ArticleBase.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )

    meta = (
        session.query(ArticleFavoriteMeta)
        .filter(ArticleFavoriteMeta.user_id == user_id, ArticleFavoriteMeta.article_id == article_id)
        .first()
    )
    now = datetime.now()
    if not meta:
        meta = ArticleFavoriteMeta(
            user_id=user_id,
            article_id=article_id,
            created_at=now,
            updated_at=now,
        )
        session.add(meta)

    if payload.category is not None:
        meta.category = str(payload.category or "").strip()[:128]
    if payload.tags is not None:
        meta.tags_json = json.dumps(_normalize_tags(payload.tags), ensure_ascii=False)
    if payload.open_count_inc:
        meta.open_count = int(meta.open_count or 0) + int(payload.open_count_inc or 0)
    meta.updated_at = now
    session.add(meta)
    session.commit()

    tags = []
    try:
        tags = json.loads(meta.tags_json or "[]")
        if not isinstance(tags, list):
            tags = []
    except Exception:
        tags = []

    return success_response(
        {
            "article_id": article_id,
            "category": str(meta.category or ""),
            "tags": _normalize_tags(tags),
            "open_count": int(meta.open_count or 0),
            "updated_at": str(meta.updated_at or ""),
        }
    )


@router.get("/categories", summary="获取收藏分类列表")
async def list_favorite_categories(
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)
    rows = (
        session.query(FavoriteCategory)
        .filter(FavoriteCategory.user_id == user_id)
        .order_by(FavoriteCategory.name.asc())
        .all()
    )
    return success_response({"list": [str(r.name or "").strip() for r in rows if str(r.name or "").strip()]})


@router.post("/categories", summary="新增收藏分类")
async def create_favorite_category(
    payload: FavoriteCategoryIn,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)
    name = str(payload.name or "").strip()[:128]
    if not name:
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40001, message="分类名不能为空"),
        )

    exists = (
        session.query(FavoriteCategory)
        .filter(FavoriteCategory.user_id == user_id, FavoriteCategory.name == name)
        .first()
    )
    if not exists:
        now = datetime.now()
        session.add(FavoriteCategory(user_id=user_id, name=name, created_at=now, updated_at=now))
        session.commit()

    return success_response({"name": name})


@router.get("/public", summary="公共收藏榜(跨用户聚合)")
async def list_public_favorites(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    days: int = Query(0, ge=0, le=3650, description="仅统计最近 N 天收藏；0=不限制"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)
    now = datetime.now()
    fav_base = session.query(ArticleFavorite)
    if days and days > 0:
        from datetime import timedelta

        fav_base = fav_base.filter(ArticleFavorite.created_at >= (now - timedelta(days=days)))

    agg = (
        fav_base.with_entities(
            ArticleFavorite.article_id.label("article_id"),
            func.count(func.distinct(ArticleFavorite.user_id)).label("favorite_users"),
            func.max(ArticleFavorite.created_at).label("last_favorited_at"),
        )
        .group_by(ArticleFavorite.article_id)
        .subquery()
    )

    my_fav_sub = (
        session.query(ArticleFavorite.article_id.label("article_id"))
        .filter(ArticleFavorite.user_id == user_id)
        .subquery()
    )

    # 热度分：收藏人数优先，其次点赞/分享/推荐/阅读
    hot_score = (
        func.coalesce(agg.c.favorite_users, 0) * 100
        + func.coalesce(ArticleBase.like_count, 0) * 2
        + func.coalesce(ArticleBase.share_count, 0) * 3
        + func.coalesce(ArticleBase.recommend_count, 0) * 2
        + (func.coalesce(ArticleBase.read_count, 0) / 1000)
    )

    q = (
        session.query(
            ArticleBase,
            agg.c.favorite_users,
            agg.c.last_favorited_at,
            Feed.mp_name.label("feed_name"),
            Feed.source_platform.label("source_platform"),
            Feed.source_type.label("source_type"),
            my_fav_sub.c.article_id.label("my_favorited_article_id"),
            hot_score.label("hot_score"),
        )
        .join(agg, agg.c.article_id == ArticleBase.id)
        .outerjoin(Feed, Feed.id == ArticleBase.mp_id)
        .outerjoin(my_fav_sub, my_fav_sub.c.article_id == ArticleBase.id)
        .filter(ArticleBase.status != DATA_STATUS.DELETED)
        .order_by(desc("hot_score"), desc(agg.c.favorite_users), desc(ArticleBase.publish_time))
    )

    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    items = []
    for art, fav_users, last_fav_at, feed_name, source_platform, source_type, my_fav_article_id, score in rows:
        d = art.__dict__.copy()
        d.pop("_sa_instance_state", None)
        d["mp_name"] = str(feed_name or d.get("mp_name") or "")
        d["source_platform"] = str(source_platform or d.get("source_platform") or "")
        d["source_type"] = str(source_type or d.get("source_type") or "")
        d["favorite_users"] = int(fav_users or 0)
        d["last_favorited_at"] = str(last_fav_at or "")
        d["hot_score"] = int(float(score or 0))
        d["my_favorited"] = bool(my_fav_article_id)
        items.append(d)

    return success_response(
        {
            "list": items,
            "total": total,
            "page": {"offset": offset, "limit": limit},
            "days": days,
        }
    )

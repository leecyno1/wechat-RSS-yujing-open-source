from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status as fast_status

from apis.base import error_response, success_response
from core.auth import get_current_user
from core.db import DB
from core.models.article import ArticleBase
from core.models.article_favorite import ArticleFavorite


router = APIRouter(prefix="/favorites", tags=["收藏"])


def _get_user_id(current_user: dict) -> str:
    u = current_user.get("original_user")
    return str(getattr(u, "id", "")) or current_user.get("username", "")


@router.post("/{article_id}", summary="收藏文章")
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


@router.delete("/{article_id}", summary="取消收藏")
async def unfavorite_article(
    article_id: str,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)
    session.query(ArticleFavorite).filter(
        ArticleFavorite.user_id == user_id, ArticleFavorite.article_id == article_id
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


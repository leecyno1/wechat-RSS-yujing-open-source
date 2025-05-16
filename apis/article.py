from fastapi import APIRouter, Depends, HTTPException, status, Query
from core.auth import get_current_user
from core.db import DB
from .ver import API_VERSION

router = APIRouter(prefix=f"{API_VERSION}/articles", tags=["文章管理"])
@router.get("", summary="获取文章列表")
async def get_articles(
    offset: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from sqlalchemy import text
        articles = session.execute(
            text("SELECT * FROM articles LIMIT :limit OFFSET :offset"),
            {"limit": limit, "offset": offset}
        ).fetchall()
        return {"code": 0, "data": articles}
    finally:
        session.close()

@router.get("/{article_id}", summary="获取文章详情")
async def get_article_detail(
    article_id: int,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        article = session.execute(
            "SELECT * FROM articles WHERE id = :id",
            {"id": article_id}
        ).fetchone()
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文章不存在"
            )
        return {"code": 0, "data": article}
    finally:
        session.close()
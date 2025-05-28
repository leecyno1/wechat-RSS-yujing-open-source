from fastapi import APIRouter, Depends, HTTPException, status, Query
from core.auth import get_current_user
from core.db import DB

router = APIRouter(prefix=f"/articles", tags=["文章管理"])
@router.get("", summary="获取文章列表")
async def get_articles(
    offset: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=100),
    status: str = Query(None),
    search: str = Query(None),
    mp_id: str = Query(None),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.article import Article
        from sqlalchemy import and_, or_
        
        # 构建查询条件
        query = session.query(Article)
        
        if status:
            query = query.filter(Article.status == status)
        if mp_id:
            query = query.filter(Article.mp_id == mp_id)
        if search:
            query = query.filter(
                or_(
                    Article.title.ilike(f"%{search}%"),
                    Article.content.ilike(f"%{search}%")
                )
            )
        
        # 获取总数
        total = query.count()
        
        # 分页查询（按发布时间降序）
        from sqlalchemy import desc
        articles = query.order_by(desc(Article.publish_time))\
                       .offset(offset)\
                       .limit(limit)\
                       .all()
        
        from .base import success_response
        return success_response({
            "list": articles,
            "total": total
        })
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
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        from .base import success_response
        return success_response(article)
    finally:
        session.close()

@router.delete("/{article_id}", summary="删除文章")
async def delete_article(
    article_id: int,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.article import Article
        from .base import error_response
        
        # 检查文章是否存在
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        
        # 删除文章
        session.delete(article)
        session.commit()
        
        from .base import success_response
        return success_response(None, message="文章删除成功")
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"删除文章失败: {str(e)}"
            )
        )
    finally:
        session.close()
from fastapi import APIRouter, Depends, HTTPException, status, Query
from core.auth import get_current_user
from core.db import DB
from .base import success_response, error_response
router = APIRouter(prefix=f"/mps", tags=["公众号管理"])

@router.get("", summary="获取公众号列表")
async def get_mps(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        # 获取总数
        total = session.query(Feed).count()
        # 分页查询
        feeds = session.query(Feed).order_by(Feed.id).offset(offset).limit(limit).all()
        
        # 转换为字典列表
        mp_list = [
            {
                "id": feed.id,
                "mp_id": feed.id,  # 使用id作为mp_id
                "name": feed.mp_name,
                "mp_name": feed.mp_name,
                "article_count": 0,  # 需要后续补充
                "status": feed.status
            }
            for feed in feeds
        ]
        
        return success_response({
            "list": mp_list,
            "total": total
        })
    except Exception as e:
        print(f"获取公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取公众号列表失败"
        )
    finally:
        session.close()

@router.get("/{mp_id}", summary="获取公众号详情")
async def get_mp_detail(
    mp_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from sqlalchemy import text
        mp = session.execute(
            text("SELECT * FROM mps WHERE mp_id = :id"),
            {"id": mp_id}
        ).fetchone()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40402,
                    message="公众号不存在"
                )
            )
        return success_response(mp)
    finally:
        session.close()
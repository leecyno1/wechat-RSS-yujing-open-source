from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from core.auth import get_current_user
from core.db import DB
from core.wx import search_Biz
from .base import success_response, error_response
from datetime import datetime
import core.config as cfg
router = APIRouter(prefix=f"/mps", tags=["公众号管理"])

@router.get("/search/{kw}", summary="搜索公众号")
async def search_mp(
    kw: str = "",
    limit: int = 5,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        result = search_Biz(kw)
        data={
            'list':result.get('list'),
            'page':{
                'limit':limit,
                'offset':offset
            },
            'total':result.get('total')
        }
        return success_response(data)
    except Exception as e:
        print(f"搜索公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message="搜索公众号失败"
            )
        )
    finally:
        session.close()

@router.get("", summary="获取公众号列表")
async def get_mps(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        total = session.query(Feed).count()
        mps = session.query(Feed).order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
        return success_response({
            "list": [{
                "id": mp.id,
                "mp_name": mp.mp_name,
                "mp_cover": mp.mp_cover,
                "mp_intro": mp.mp_intro,
                "status": mp.status,
                "created_at": mp.created_at.isoformat()
            } for mp in mps],
            "page": {
                "limit": limit,
                "offset": offset,
                "total": total
            },
            "total": total
        })
    except Exception as e:
        print(f"获取公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message="获取公众号列表失败"
            )
        )
    finally:
        session.close()

@router.get("/update/{mp_id}", summary="更新公众号文章")
async def update_mps(
     mp_id: str,
    # current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        from core.wx import get_list
        import time
        time_span=int(time.time())-mp.update_time
        if time_span<cfg.get("sync_interval",60*60):
           raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40402,
                    message="请不要频繁更新操作",
                    data={"time_span":time_span}
                )
            )
            


        result=get_list(faker_id= mp.faker_id, mp_id=mp.id ,is_add=True)
        return success_response({
            "time_span":time_span,
            "list":result,
            "total":len(result),
            "mps":mp
        })
    except Exception as e:
        print(f"获取公众号详情错误: {str(e)}",e)
        # raise HTTPException(
        #     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        #     detail=error_response(
        #         code=50001,
        #         message=f"获取公众号详情失败{str(e)}"
        #     )
        # )
        raise e
    finally:
        session.close()
    pass

@router.get("/{mp_id}", summary="获取公众号详情")
async def get_mp(
    mp_id: str,
    # current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        return success_response(mp)
    except Exception as e:
        print(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message="获取公众号详情失败"
            )
        )
    finally:
        session.close()

@router.post("", summary="添加公众号")
async def add_mp(
    mp_name: str = Body(..., min_length=1, max_length=255),
    mp_cover: str = Body(None, max_length=255),
    mp_id: str = Body(None, max_length=255),
    avatar: str = Body(None, max_length=500),
    mp_intro: str = Body(None, max_length=255),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        now = datetime.now()
        
        # 创建新的Feed记录
        new_feed = Feed(
            id=f"mp_{now.timestamp()}",
            mp_name=mp_name,
            mp_cover=avatar,
            mp_intro=mp_intro,
            status=1,  # 默认启用状态
            created_at=now,
            updated_at=now,
            faker_id=mp_id,
            update_time=now.timestamp(),
            sync_time=now.timestamp(),
        )
        
        session.add(new_feed)
        session.commit()
        
        return success_response({
            "id": new_feed.id,
            "mp_name": new_feed.mp_name,
            "mp_cover": new_feed.mp_cover,
            "mp_intro": new_feed.mp_intro,
            "status": new_feed.status,
            "faker_id":mp_id,
            "created_at": new_feed.created_at.isoformat()
        })
    except Exception as e:
        session.rollback()
        print(f"添加公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message="添加公众号失败"
            )
        )
    finally:
        session.close()
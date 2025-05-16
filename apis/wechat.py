from fastapi import APIRouter, Depends, HTTPException, status, Query
from core.auth import get_current_user
from core.db import DB
from .ver import API_VERSION
router = APIRouter(prefix=f"{API_VERSION}/mps", tags=["公众号管理"])

@router.get("", summary="获取公众号列表")
async def get_mps(current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    try:
        mps = DB.get_all_mps()
        return {"code": 0, "data": mps}
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
                detail="公众号不存在"
            )
        return {"code": 0, "data": mp}
    finally:
        session.close()
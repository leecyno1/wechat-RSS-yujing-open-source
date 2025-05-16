from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from datetime import datetime
from core.auth import get_current_user
from core.db import DB
from core.models import User as DBUser
from core.auth import pwd_context
import os

router = APIRouter(prefix="/wx/user", tags=["用户管理"])

@router.get("", summary="获取用户信息")
async def get_user_info(current_user: dict = Depends(get_current_user)):
    session = DB.get_session()
    try:
        user = session.query(DBUser).filter(
            DBUser.username == current_user["username"]
        ).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        return {
            "code": 0,
            "data": {
                "username": user.username,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at
            }
        }
    finally:
        session.close()

@router.put("", summary="修改用户资料")
async def update_user_info(
    update_data: dict,
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        user = session.query(DBUser).filter(
            DBUser.username == current_user["username"]
        ).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        if "password" in update_data:
            user.password_hash = pwd_context.hash(update_data["password"])
        if "is_active" in update_data:
            user.is_active = bool(update_data["is_active"])
        
        user.updated_at = datetime.now()
        session.commit()
        
        return {"code": 0, "message": "更新成功"}
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    finally:
        session.close()

@router.post("/avatar", summary="上传用户头像")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """处理用户头像上传"""
    try:
        # 确保头像目录存在
        os.makedirs("static/avatars", exist_ok=True)
        
        # 保存文件
        file_path = f"static/avatars/{current_user['username']}.jpg"
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        
        return {
            "code": 0,
            "url": f"/avatars/{current_user['username']}.jpg"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"头像上传失败: {str(e)}"
        )
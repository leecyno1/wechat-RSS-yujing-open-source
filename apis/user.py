from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from datetime import datetime
from core.auth import get_current_user
from core.db import DB
from core.models import User as DBUser
from core.auth import pwd_context
import os

router = APIRouter(prefix="/user", tags=["用户管理"])

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
        from .base import success_response
        return success_response({
            "username": user.username,
            "nickname": user.nickname if user.nickname else user.username,
            "avatar": user.avatar if user.avatar else "/static/default-avatar.png",
            "email": user.email if user.email else "",
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })
    finally:
        session.close()

@router.put("", summary="修改用户资料")
async def update_user_info(
    update_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """修改用户基本信息(不包括密码)"""
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
        
        # 不允许通过此接口修改密码
        if "password" in update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请使用专门的密码修改接口"
            )
            
        if "is_active" in update_data:
            user.is_active = bool(update_data["is_active"])
        
        user.updated_at = datetime.now()
        session.commit()
        
        return {"code": 0, "message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"更新用户信息失败: {str(e)}"
        )
    finally:
        session.close()

@router.put("/password", summary="修改密码")
async def change_password(
    password_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """修改用户密码"""
    session = DB.get_session()
    try:
        # 验证请求数据
        if "old_password" not in password_data or "new_password" not in password_data:
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40001,
                    message="需要提供旧密码和新密码"
                )
            )
            
        # 获取用户
        user = session.query(DBUser).filter(
            DBUser.username == current_user["username"]
        ).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
            
        # 验证旧密码
        if not pwd_context.verify(password_data["old_password"], user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="旧密码不正确"
            )
            
        # 验证新密码复杂度
        new_password = password_data["new_password"]
        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="密码长度不能少于8位"
            )
            
        # 更新密码
        user.password_hash = pwd_context.hash(new_password)
        user.updated_at = datetime.now()
        session.commit()
        
        from .base import success_response
        return success_response(message="密码修改成功")
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"密码修改失败: {str(e)}"
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
        
        # 更新用户头像字段
        session = DB.get_session()
        try:
            user = session.query(DBUser).filter(
                DBUser.username == current_user["username"]
            ).first()
            if user:
                user.avatar = f"/avatars/{current_user['username']}.jpg"
                session.commit()
        
        finally:
            session.close()

        return {
            "code": 0,
            "data": {
                "avatar": f"/avatars/{current_user['username']}.jpg"
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"头像上传失败: {str(e)}"
        )
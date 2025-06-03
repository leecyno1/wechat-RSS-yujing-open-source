from pydantic import BaseModel

# 标准导入分组和顺序
# 1. 标准库导入
from datetime import datetime
from typing import List, Optional

# 2. 第三方库导入
from fastapi import APIRouter, Depends, HTTPException, status,Body,Query
from sqlalchemy.orm import Session

# 3. 本地应用/模块导入
from core.auth import get_current_user
from core.db import DB
from core.models.message_task import MessageTask
from .base import success_response, error_response

router = APIRouter(prefix="/message_tasks", tags=["消息任务"])

@router.get("", summary="获取消息任务列表")
async def list_message_tasks(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
):
    db=DB.get_session()
    """
    获取消息任务列表
    
    参数:
        skip: 跳过的记录数，用于分页
        limit: 每页返回的最大记录数
        status: 可选，按状态筛选任务
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含消息任务列表的成功响应，或错误响应
        
    异常:
        数据库查询异常: 返回500内部服务器错误
    """
    try:
        query = db.query(MessageTask)
        if status is not None:
            query = query.filter(MessageTask.status == status)
        
        total = query.count()
        message_tasks = query.offset(offset).limit(limit).all()
        
        return success_response({
            "list": message_tasks,
            "page": {
                "limit": limit,
                "offset": offset
            },
            "total": total
        })
    except Exception as e:
        return error_response(code=500, message=str(e))

@router.get("/{task_id}", summary="获取单个消息任务详情")
async def get_message_task(
    task_id: int,
    current_user: dict = Depends(get_current_user)
):
    db=DB.get_session()
    """
    获取单个消息任务详情
    
    参数:
        task_id: 消息任务ID
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含消息任务详情的成功响应，或错误响应
        
    异常:
        404: 消息任务不存在
        500: 数据库查询异常
    """
    try:
        message_task = db.query(MessageTask).filter(MessageTask.id == task_id).first()
        if not message_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        return success_response(data=message_task)
    except Exception as e:
        return error_response(code=500, message=str(e))


class MessageTaskCreate(BaseModel):
    message_template: str
    web_hook_url: str
    mps_id: str=""
    name: str=""
    message_type: int=0
    cron_exp:str=""
    status: Optional[int] = 0

@router.post("", summary="创建消息任务", status_code=status.HTTP_201_CREATED)
async def create_message_task(
    task_data: MessageTaskCreate = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    创建新消息任务
    
    参数:
        task_data: 消息任务创建数据
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        201: 包含新创建消息任务的响应
        400: 请求数据验证失败
        500: 数据库操作异常
    """
    db=DB.get_session()
    try:
        db_task = MessageTask(
            message_template=task_data.message_template,
            web_hook_url=task_data.web_hook_url,
            cron_exp=task_data.cron_exp,
            mps_id=task_data.mps_id,
            message_type=task_data.message_type,
            name=task_data.name,
            status=task_data.status if task_data.status is not None else 0
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        return success_response(data=db_task)
    except Exception as e:
        db.rollback()
        return error_response(code=500, message=str(e))

@router.put("/{task_id}", summary="更新消息任务")
async def update_message_task(
    task_id: int,
    task_data: MessageTaskCreate = Body(...),
    current_user: dict = Depends(get_current_user)
):
    db=DB.get_session()
    """
    更新消息任务
    
    参数:
        task_id: 要更新的消息任务ID
        task_data: 消息任务更新数据
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含更新后消息任务的响应
        404: 消息任务不存在
        400: 请求数据验证失败
        500: 数据库操作异常
    """
    try:
        db_task = db.query(MessageTask).filter(MessageTask.id == task_id).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        
        if task_data.message_template is not None:
            db_task.message_template = task_data.message_template
        if task_data.web_hook_url is not None:
            db_task.web_hook_url = task_data.web_hook_url
        if task_data.mps_id is not None:
            db_task.mps_id = task_data.mps_id
        if task_data.status is not None:
            db_task.status = task_data.status
        if task_data.cron_exp is not None:
            db_task.cron_exp = task_data.cron_exp
        if task_data.message_type is not None:
            db_task.message_type = task_data.message_type
        if task_data.name is not None:
            db_task.name = task_data.name
        db.commit()
        db.refresh(db_task)
        return success_response(data=db_task)
    except Exception as e:
        db.rollback()
        return error_response(code=500, message=str(e))

@router.delete("/{task_id}",summary="删除消息任务")
async def delete_message_task(
    task_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    删除消息任务
    
    参数:
        task_id: 要删除的消息任务ID
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        204: 成功删除，无返回内容
        404: 消息任务不存在
        500: 数据库操作异常
    """
    db=DB.get_session()
    try:
        db_task = db.query(MessageTask).filter(MessageTask.id == task_id).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        
        db.delete(db_task)
        db.commit()
        return success_response(message="Message task deleted successfully")
    except Exception as e:
        db.rollback()
        return error_response(code=500, message=str(e))
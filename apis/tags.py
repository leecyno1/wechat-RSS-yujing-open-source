from fastapi import APIRouter, Depends, HTTPException,status
from typing import List
from datetime import datetime
import json
import uuid
from core.models.tags import Tags as TagsModel
from core.models.user import User as UserModel
from core.database import get_db
from sqlalchemy.orm import Session
from schemas.tags import Tags, TagsCreate
from .base import success_response, error_response
from core.auth import get_current_user, requires_permission
from sqlalchemy import or_

# 标签管理API路由
# 提供标签的增删改查功能
# 需要管理员权限执行写操作
router = APIRouter(prefix="/tags", tags=["标签管理"])


def _uid(current_user: dict) -> str:
    try:
        return str(current_user.get("original_user").id)
    except Exception:
        return str(current_user.get("username") or "")


def _is_admin(current_user: dict) -> bool:
    try:
        return str(current_user.get("role") or "") == "admin" or str(current_user.get("username") or "") == "admin"
    except Exception:
        return False


def _normalize_mps_text(raw) -> str:
    if raw is None:
        return "[]"
    if isinstance(raw, (list, dict)):
        value = raw
    else:
        text = str(raw).strip()
        if not text:
            return "[]"
        try:
            value = json.loads(text)
        except Exception:
            return text

    if isinstance(value, list):
        try:
            value = sorted(
                value,
                key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True)
            )
        except Exception:
            pass
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _mp_count(mps_text: str) -> int:
    try:
        payload = json.loads(str(mps_text or "[]"))
        if isinstance(payload, list):
            return len(payload)
    except Exception:
        pass
    return 0

@router.get("", 
    summary="获取标签列表",
    description="分页获取所有标签信息")
async def get_tags(offset: int = 0, limit: int = 100, db: Session = Depends(get_db),cur_user: dict = Depends(get_current_user)):
    """
    获取标签列表
    
    参数:
    - offset: 跳过记录数，用于分页
    - limit: 每页记录数，默认100
    
    返回:
    - 包含标签列表和分页信息的成功响应
    """
    user_id = _uid(cur_user)
    if _is_admin(cur_user):
        query = db.query(TagsModel).filter(or_(TagsModel.user_id == user_id, TagsModel.user_id.is_(None)))
    else:
        query = db.query(TagsModel).filter(TagsModel.user_id == user_id)
    total = query.count()
    tags = query.offset(offset).limit(limit).all()
    return success_response(data={
        "list": tags,
        "page": {
            "limit": limit,
            "offset": offset,
            "total": total
        },
        "total": total
    })


@router.get("/plaza",
    summary="获取频道广场",
    description="获取所有用户创建的公开频道列表")
async def get_tag_plaza(
    offset: int = 0,
    limit: int = 100,
    keyword: str = "",
    db: Session = Depends(get_db),
    cur_user: dict = Depends(get_current_user)
):
    query = (
        db.query(TagsModel, UserModel.username, UserModel.nickname)
        .outerjoin(UserModel, TagsModel.user_id == UserModel.id)
        .filter(TagsModel.status == 1)
    )
    kw = str(keyword or "").strip()
    if kw:
        rule = or_(TagsModel.name.like(f"%{kw}%"), TagsModel.intro.like(f"%{kw}%"))
        query = query.filter(rule)
    total = query.count()
    rows = (
        query.order_by(TagsModel.updated_at.desc(), TagsModel.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    current_uid = _uid(cur_user)
    items = []
    for tag, username, nickname in rows:
        creator_display = str(nickname or "").strip() or str(username or "").strip() or "官方频道"
        items.append({
            "id": tag.id,
            "name": tag.name,
            "cover": tag.cover,
            "intro": tag.intro,
            "mps_id": tag.mps_id,
            "status": tag.status,
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
            "user_id": tag.user_id,
            "creator_username": username or "",
            "creator_nickname": nickname or "",
            "creator_display": creator_display,
            "mp_count": _mp_count(tag.mps_id),
            "is_mine": str(tag.user_id or "") == current_uid,
        })
    return success_response(data={
        "list": items,
        "page": {
            "limit": limit,
            "offset": offset,
            "total": total
        },
        "total": total
    })


@router.post("/plaza/{tag_id}/use",
    summary="使用频道广场频道",
    description="复制广场频道到我的频道")
async def use_tag_from_plaza(tag_id: str, db: Session = Depends(get_db), cur_user: dict = Depends(get_current_user)):
    user_id = _uid(cur_user)
    source = db.query(TagsModel).filter(TagsModel.id == tag_id, TagsModel.status == 1).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="频道不存在或已停用"),
        )

    source_name = str(source.name or "").strip()
    normalized_source_mps = _normalize_mps_text(source.mps_id)
    mine = db.query(TagsModel).filter(TagsModel.user_id == user_id).all()
    for item in mine:
        if str(item.name or "").strip() != source_name:
            continue
        if _normalize_mps_text(item.mps_id) == normalized_source_mps:
            return success_response(data=item, message="该频道已在我的频道中")

    copied = TagsModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=source.name or "",
        cover=source.cover or "",
        intro=source.intro or "",
        mps_id=source.mps_id or "[]",
        status=1,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.add(copied)
    db.commit()
    db.refresh(copied)
    return success_response(data=copied, message="已添加到我的频道")

@router.post("",
    summary="创建新标签",
    description="创建一个新的标签"
   )
async def create_tag(tag: TagsCreate, db: Session = Depends(get_db),cur_user: dict = Depends(get_current_user)):
    """
    创建新标签
    
    参数:
    - tag: TagsCreate模型，包含标签信息
    
    请求体示例:
    {
        "name": "新标签",
        "cover": "http://example.com/cover.jpg",
        "intro": "新标签的描述",
        "status": 1
    }
    
    返回:
    - 成功: 包含新建标签信息的响应
    - 失败: 错误响应
    """
    try:
        user_id = _uid(cur_user)
        db_tag = TagsModel(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=tag.name or '',
            cover=tag.cover or '',
            intro=tag.intro or '',
            mps_id =tag.mps_id,
            status=tag.status,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(db_tag)
        db.commit()
        db.refresh(db_tag)
        return success_response(data=db_tag)
    except Exception as e:
         from core.print  import print_error
         print_error(e)
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message=f"暂无数据",
            )
        )

@router.get("/{tag_id}", summary="获取单个标签详情",  description="根据标签ID获取标签详细信息")
async def get_tag(tag_id: str, db: Session = Depends(get_db),cur_user: dict = Depends(get_current_user)):
    """
    获取单个标签详情
    
    参数:
    - tag_id: 标签ID
    
    返回:
    - 成功: 包含标签详情的响应
    - 失败: 201错误响应(标签不存在)
    """
    user_id = _uid(cur_user)
    q = db.query(TagsModel).filter(TagsModel.id == tag_id)
    if _is_admin(cur_user):
        q = q.filter(or_(TagsModel.user_id == user_id, TagsModel.user_id.is_(None)))
    else:
        q = q.filter(TagsModel.user_id == user_id)
    tag = q.first()
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="Tag not found"),
        )
    return success_response(data=tag)

@router.put("/{tag_id}",
    summary="更新标签信息",
    description="根据标签ID更新标签信息",
 )
async def update_tag(tag_id: str, tag_data: TagsCreate, db: Session = Depends(get_db),cur_user: dict = Depends(get_current_user)):
    """
    更新标签信息
    
    参数:
    - tag_id: 要更新的标签ID
    - tag_data: TagsCreate模型，包含要更新的标签信息
    
    请求体示例:
    {
        "name": "更新后的标签",
        "cover": "http://example.com/new_cover.jpg",
        "intro": "更新后的描述",
        "status": 1
    }
    
    返回:
    - 成功: 包含更新后标签信息的响应
    - 失败: 404错误响应(标签不存在)或500错误响应(服务器错误)
    """
    try:
        user_id = _uid(cur_user)
        q = db.query(TagsModel).filter(TagsModel.id == tag_id)
        if _is_admin(cur_user):
            q = q.filter(or_(TagsModel.user_id == user_id, TagsModel.user_id.is_(None)))
        else:
            q = q.filter(TagsModel.user_id == user_id)
        tag = q.first()
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="Tag not found"),
            )
        
        tag.name = tag_data.name
        tag.cover = tag_data.cover
        tag.intro = tag_data.intro
        tag.status = tag_data.status
        tag.mps_id = tag_data.mps_id
        if tag.user_id is None:
            tag.user_id = user_id
        tag.updated_at = datetime.now()
        
        db.commit()
        db.refresh(tag)
        return success_response(data=tag)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=str(e)),
        )

@router.delete("/{tag_id}",
    summary="删除标签",
    description="根据标签ID删除标签",
   )
async def delete_tag(tag_id: str, db: Session = Depends(get_db),cur_user: dict = Depends(get_current_user)):
    """
    删除标签
    
    参数:
    - tag_id: 要删除的标签ID
    
    返回:
    - 成功: 删除成功的响应
    - 失败: 404错误响应(标签不存在)或500错误响应(服务器错误)
    """
    try:
        user_id = _uid(cur_user)
        q = db.query(TagsModel).filter(TagsModel.id == tag_id)
        if _is_admin(cur_user):
            q = q.filter(or_(TagsModel.user_id == user_id, TagsModel.user_id.is_(None)))
        else:
            q = q.filter(TagsModel.user_id == user_id)
        tag = q.first()
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="Tag not found"),
            )
        db.delete(tag)
        db.commit()
        return success_response(message="Tag deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=str(e)),
        )

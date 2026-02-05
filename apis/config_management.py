from fastapi import APIRouter, Depends, HTTPException,Body,Path,Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from core.models.config_management import ConfigManagement
from core.db  import DB
from core.auth import get_current_user
from .base import  success_response, error_response
from core.config import cfg
router = APIRouter(prefix="/configs", tags=["配置管理"])


def _require_admin(current_user: dict) -> None:
    role = str((current_user or {}).get("role") or "")
    username = str((current_user or {}).get("username") or "")
    if role == "admin" or username == "admin":
        return
    raise HTTPException(status_code=403, detail=error_response(code=40301, message="仅管理员可访问配置管理"))


@router.get("",summary="获取配置项列表")
def list_configs(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    # db=DB.get_session()
    """获取配置项列表"""
    try:
        _require_admin(current_user)
        # total = db.query(ConfigManagement).count()
        # configs = db.query(ConfigManagement).offset(offset).limit(limit).all()
        from core.yaml_db import YamlDB
        configs = YamlDB.store_config_to_list(cfg._config) 
        total=len(configs)
        return success_response(data={
            "list": configs,
            "page": {
                    "limit": limit,
                    "offset": offset
                },
                "total": total
        })
    except Exception as e:
        return error_response(code=500, message=str(e))

@router.get("/{config_key}", summary="获取单个配置项详情")
def get_config(
    config_key: str,
    current_user: dict = Depends(get_current_user)
):
    """获取单个配置项详情"""
    try:
        _require_admin(current_user)
        val = cfg.get(config_key, None)
        return success_response(
            data=ConfigManagement(
                config_key=config_key,
                config_value=str(val) if val is not None else "",
                description="系统配置项",
            )
        )
    except Exception as e:
        return error_response(code=500, message=str(e))

class ConfigManagementCreate(BaseModel):
    config_key: str
    config_value: str
    description: Optional[str] = None

@router.post("", summary="创建配置项")
def create_config(
    config_data: ConfigManagementCreate = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """创建配置项"""
    try:
        _require_admin(current_user)
        cfg.set_path(config_data.config_key, config_data.config_value)
        return success_response(
            data=ConfigManagement(
                config_key=config_data.config_key,
                config_value=str(cfg.get(config_data.config_key, "")),
                description=config_data.description,
            )
        )
    except Exception as e:
        return error_response(code=500, message=str(e))

@router.put("/{config_key}", summary="更新配置项")
def update_config(
    config_key: str=Path(...,min_length=1),
    config_data: ConfigManagementCreate = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """更新配置项"""
    try:
        _require_admin(current_user)
        if config_data.config_value is not None:
            cfg.set_path(config_key, config_data.config_value)
        return success_response(
            data=ConfigManagement(
                config_key=config_key,
                config_value=str(cfg.get(config_key, "")),
                description=config_data.description,
            )
        )
    except Exception as e:
        return error_response(code=500, message=str(e))

@router.delete("/{config_key}",summary="删除配置项")
def delete_config(
    config_key: str,
    current_user: dict = Depends(get_current_user)
):
    """删除配置项"""
    try:
        _require_admin(current_user)
        cfg.delete_path(config_key)
        return success_response(message="Config override deleted successfully")
    except Exception as e:
        return error_response(code=500, message=str(e))

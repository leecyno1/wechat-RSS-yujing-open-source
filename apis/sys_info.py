import platform
import time
import sys
from fastapi import APIRouter,Depends
from typing import Dict, Any
from core.auth import get_current_user
from .base import success_response, error_response

router = APIRouter(prefix="/sys", tags=["系统信息"])

# 记录服务器启动时间
_START_TIME = time.time()

@router.get("/info", summary="获取系统信息")
async def get_system_info(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """获取当前系统的各种信息
    
    Returns:
        BaseResponse格式的系统信息，包括:
        - os: 操作系统信息
        - python_version: Python版本
        - uptime: 服务器运行时间(秒)
        - system: 系统详细信息
    """
    try:
        from .ver import API_VERSION
        from core.ver import VERSION as CORE_VERSION,LATEST_VERSION
        # 获取系统信息
        system_info = {
            'os': {
                'name': platform.system(),
                'version': platform.version(),
                'release': platform.release(),
            },
            'python_version': sys.version,
            'uptime': round(time.time() - _START_TIME, 2),
            'system': {
                'node': platform.node(),
                'machine': platform.machine(),
                'processor': platform.processor(),
            },
            'api_version': API_VERSION,
            'core_version': CORE_VERSION,
            'latest_version':LATEST_VERSION,
            'need_update':CORE_VERSION != LATEST_VERSION
        }
        return success_response(data=system_info)
    except Exception as e:
        return error_response(
            code=50001,
            message=f"获取系统信息失败: {str(e)}"
        )
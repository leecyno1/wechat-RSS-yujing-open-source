import platform
import time
import sys
import psutil
import os
from fastapi import APIRouter,Depends
from typing import Dict, Any
from core.auth import get_current_user
from .base import success_response, error_response
from driver.token import wx_cfg
from core.config import cfg
from jobs.mps import TaskQueue
from driver.success import getLoginInfo,getStatus
from fastapi.responses import Response
from io import BytesIO
import qrcode
router = APIRouter(prefix="/sys", tags=["系统信息"])
def get_docker_version():
        try:
            with open("./docker_version.txt", "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            return "未知"
# 记录服务器启动时间
_START_TIME = time.time()
@router.get("/base_info", summary="常规信息")
async def get_base_info() -> Dict[str, Any]:
    try:
        from .ver import API_VERSION
        from core.config import VERSION as CORE_VERSION,LATEST_VERSION
       
        base_info = {
            'api_version': API_VERSION,
            'docker_version': get_docker_version(),
            'core_version': CORE_VERSION,
            "ui":{
                "name": cfg.get("server.name",""),
                "web_name": cfg.get("server.web_name","WeRss公众号订阅平台"),
            }
        }
        return success_response(data=base_info)
    except Exception as e:
        return error_response(
            code=50001,
            message=f"获取信息失败: {str(e)}"
        )    
    

_PROMO_QR_CACHE: dict[str, Any] = {"url": None, "png": None}


@router.get("/promo/qr", summary="推广二维码(关注公众号)")
async def promo_qr() -> Response:
    """Return PNG QR code for promo.qr_url (or PROMO_QR_URL env via config)."""
    qr_file = str(cfg.get("promo.qr_file", "static/promo/lemon_doctor_qr.jpg") or "static/promo/lemon_doctor_qr.jpg").strip()
    if qr_file and os.path.exists(qr_file):
        try:
            with open(qr_file, "rb") as f:
                data = f.read()
            if not data:
                return Response(status_code=404, content=b"", media_type="image/png")
            ext = os.path.splitext(qr_file)[-1].lower()
            media_type = "image/png"
            if ext in (".jpg", ".jpeg"):
                media_type = "image/jpeg"
            elif ext == ".webp":
                media_type = "image/webp"
            return Response(content=data, media_type=media_type)
        except Exception:
            pass

    url = str(cfg.get("promo.qr_url", "") or "").strip()
    if not url:
        # Keep it as an image endpoint: return 404 to avoid breaking <img> silently.
        return Response(status_code=404, content=b"", media_type="image/png")

    cached_url = _PROMO_QR_CACHE.get("url")
    cached_png = _PROMO_QR_CACHE.get("png")
    if cached_url == url and isinstance(cached_png, (bytes, bytearray)) and cached_png:
        return Response(content=bytes(cached_png), media_type="image/png")

    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    png = buf.getvalue()
    _PROMO_QR_CACHE["url"] = url
    _PROMO_QR_CACHE["png"] = png
    return Response(content=png, media_type="image/png")


from core.resource import get_system_resources
@router.get("/resources", summary="获取系统资源使用情况")
async def system_resources(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """获取系统资源使用情况
    
    Returns:
        BaseResponse格式的资源使用信息，包括:
        - cpu: CPU使用率(%)
        - memory: 内存使用情况
        - disk: 磁盘使用情况
    """
    try:
        resources_info=get_system_resources()
        resources_info["queue"]=TaskQueue.get_queue_info(),
        return success_response(data=resources_info)
    except Exception as e:
        return error_response(
            code=50002,
            message=f"获取系统资源失败: {str(e)}"
        )
from core.article_lax import laxArticle
from .ver import API_VERSION
from core.base import VERSION as CORE_VERSION,LATEST_VERSION
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
      
        wx_cfg.reload()
        # 获取系统信息
        system_info = {
            'os': {
                'name': platform.system(),
                'version': platform.version(),
                'docker_version': get_docker_version(),
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
            'need_update':CORE_VERSION != LATEST_VERSION,
            "wx":{
                'token':wx_cfg.get('token',''),
                'expiry_time':wx_cfg.get('expiry.expiry_time','') if getStatus() else "",
                "info":getLoginInfo(),
                "login":getStatus(),
            },
            "article": laxArticle(),
            'queue':TaskQueue.get_queue_info(),
        }
        return success_response(data=system_info)
    except Exception as e:
        return error_response(
            code=50001,
            message=f"获取系统信息失败: {str(e)}"
        )

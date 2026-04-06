from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from core.auth import get_current_user
from core.db import DB
from .base import success_response, error_response,BaseResponse
from datetime import datetime
from typing import Optional, List
import os
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 导入导出工具
from tools.mdtools.export import export_md_to_doc, process_articles

router = APIRouter(prefix="/tools", tags=["工具"])

# Schema 模型定义
class ExportArticlesRequest(BaseModel):
    """导出文章请求模型"""
    mp_id: str = Field("", description="公众号ID（可逗号分隔；为空表示全部订阅）", example="MP_WXS_3892772220")
    export_scope: str = Field("selected", description="导出范围：selected/all_subscriptions")
    export_key: Optional[str] = Field(None, description="导出记录分组键（用于导出目录）")
    doc_id: Optional[List[str]] = Field(None, description="文档ID列表，为空则导出所有文章", example=[])
    page_size: int = Field(10, description="每页数量", ge=1, le=10)
    page_count: int = Field(1, description="页数，0表示全部", ge=0, le=10000)
    add_title: bool = Field(True, description="是否添加标题")
    remove_images: bool = Field(True, description="是否移除图片")
    remove_links: bool = Field(False, description="是否移除链接")
    export_md: bool = Field(False, description="是否导出Markdown格式")
    export_docx: bool = Field(False, description="是否导出Word文档格式")
    export_json: bool = Field(False, description="是否导出JSON格式")
    export_csv: bool = Field(False, description="是否导出CSV格式")
    export_pdf: bool = Field(True, description="是否导出PDF格式")
    zip_filename: Optional[str] = Field(None, description="压缩包文件名，为空则自动生成", example="")

class ExportArticlesResponse(BaseModel):
    """导出文章响应模型"""
    record_count: int = Field(..., description="导出的文章数量")
    export_path: str = Field(..., description="导出文件路径")
    message: str = Field(..., description="导出结果消息")

class ExportFileInfo(BaseModel):
    """导出文件信息模型"""
    filename: str = Field(..., description="文件名")
    size: int = Field(..., description="文件大小（字节）")
    created_time: str = Field(..., description="创建时间（ISO格式）")
    modified_time: str = Field(..., description="修改时间（ISO格式）")

def _export_articles_worker(
    mp_id: str,
    export_key: Optional[str],
    doc_id: Optional[List[int]],
    page_size: int,
    page_count: int,
    add_title: bool,
    remove_images: bool,
    remove_links: bool,
    export_md: bool,
    export_docx: bool,
    export_json: bool,
    export_csv: bool,
    export_pdf: bool,
    zip_filename: Optional[str]
):
    """
    导出文章的工作线程函数
    """
    return export_md_to_doc(
        mp_id=mp_id,
        export_key=export_key,
        doc_id=doc_id,
        page_size=page_size,
        page_count=page_count,
        add_title=add_title,
        remove_images=remove_images,
        remove_links=remove_links,
        export_md=export_md,
        export_docx=export_docx,
        export_json=export_json,
        export_csv=export_csv,
        export_pdf=export_pdf,
        zip_filename=zip_filename
    )

@router.post("/export/articles", summary="导出文章")
async def export_articles(
    request: ExportArticlesRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    导出文章为多种格式（使用线程池异步处理）
    """
    try:
        scope = str(request.export_scope or "selected").strip().lower()
        mp_scope = str(request.mp_id or "").strip()
        if scope == "all_subscriptions":
            mp_scope = ""
        export_key = str(request.export_key or "").strip()
        if not export_key:
            export_key = "all_subscriptions" if not mp_scope else mp_scope

        # 检查是否已有同一导出分组的任务正在运行
        for thread in threading.enumerate():
            if thread.name == f"export_articles_{export_key}":
                raise HTTPException(
                    status_code=400,
                    detail=error_response(40001, "该导出分组任务已在处理中，请勿重复点击"),
                )
                
        # 直接生成 zip_filename 并返回
        docx_path = f"./data/docs/{export_key}/"
        if request.zip_filename:
            zip_file_path = f"{docx_path}{request.zip_filename}"
        else:
            zip_file_path = f"{docx_path}exported_articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        # 启动后台线程执行导出操作
        export_thread = threading.Thread(
            target=_export_articles_worker,
            args=(
                mp_scope,
                export_key,
                request.doc_id,
                request.page_size,
                request.page_count,
                request.add_title,
                request.remove_images,
                request.remove_links,
                request.export_md,
                request.export_docx,
                request.export_json,
                request.export_csv,
                request.export_pdf,
                request.zip_filename
            ),
            name=f"export_articles_{export_key}"
        )
        export_thread.start()
        
        return success_response({
            "export_path": zip_file_path,
            "message": "导出任务已启动，请稍后下载文件"
        })
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=error_response(40001, str(e)))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(50000, f"导出失败: {str(e)}"))

@router.get("/export/download", summary="下载导出文件")
async def download_export_file(
    filename: str = Query(..., description="文件名"),
    mp_id: Optional[str] = Query(None, description="公众号ID"),
    delete_after_download: bool = Query(False, description="下载后删除文件"),
    # current_user: dict = Depends(get_current_user)
):
    """
    下载导出的文件
    """
    try:
        # 定义基础目录
        base_dir = os.path.abspath("./data/docs")
        
        # 构建并规范化路径
        if mp_id:
            target_path = os.path.join(base_dir, mp_id, filename)
        else:
            # 如果没有mp_id，可能是在根目录下或者是旧逻辑，视需求而定
            # 这里为了安全起见，依然限制在 base_dir 下
            target_path = os.path.join(base_dir, filename)

        # 获取绝对路径
        safe_path = os.path.abspath(target_path)

        # 检查是否尝试跳出基础目录
        if not safe_path.startswith(base_dir):
            raise HTTPException(status_code=403, detail=error_response(40301, "非法的文件路径请求"))

        if not os.path.exists(safe_path):
            # 避免泄露文件存在信息，或者直接报404
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 再次确认是文件而不是目录
        if not os.path.isfile(safe_path):
            raise HTTPException(status_code=404, detail="文件不存在")

        def cleanup_file():
            """后台任务：删除临时文件"""
            try:
                if os.path.exists(safe_path) and delete_after_download:
                    os.remove(safe_path)
            except Exception:
                pass
        
        return FileResponse(
            path=safe_path,
            filename=filename,
            background=BackgroundTask(cleanup_file)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(50000, f"下载失败: {str(e)}"))

@router.get("/export/list", summary="获取导出文件列表", response_model=BaseResponse)
async def list_export_files(
    mp_id: Optional[str] = Query(None, description="公众号ID"),
    export_key: Optional[str] = Query(None, description="导出分组键"),
    current_user: dict = Depends(get_current_user)
):
    """
    获取指定公众号的导出文件列表
    """
    try:
        from .ver import API_VERSION
        safe_root = os.path.abspath(os.path.normpath("./data/docs"))
        key = str(export_key or mp_id or "").strip() or "all_subscriptions"
        export_path = os.path.abspath(os.path.join(safe_root, key))
        # Validate that export_path is within safe_root
        if not export_path.startswith(safe_root):
            return success_response([])
        if not os.path.exists(export_path):
            return success_response([])
        # Check directory permissions
        if not os.access(export_path, os.R_OK):
            raise HTTPException(status_code=403, detail=error_response(40301, "无权限访问该目录"))
        files = []
        for root, _, filenames in os.walk(export_path):
            # Ensure root is also within safe_root, in case of symlinks or traversal
            root_norm = os.path.abspath(root)
            if not root_norm.startswith(safe_root):
                continue
            for filename in filenames:
                if filename.endswith('.zip'):
                    file_path = os.path.join(root, filename)
                    try:
                        file_stat = os.stat(file_path)
                        file_path = os.path.relpath(file_path, export_path)
                        files.append({
                        "filename": filename,
                        "size": file_stat.st_size,
                        "created_time": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                        "modified_time": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                        "path": file_path,
                        "download_url": f"{API_VERSION}/tools/export/download?mp_id={key}&filename={file_path}"  # 下载链接
                    })
                    except PermissionError:
                        continue
               
        
        # 按修改时间倒序排列
        files.sort(key=lambda x: x["modified_time"], reverse=True)
        
        return success_response(files)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(50000, f"获取文件列表失败: {str(e)}"))

# 删除文件请求模型
class DeleteFileRequest(BaseModel):
    """删除文件请求模型"""
    filename: str = Field(..., description="文件名", example="exported_articles_20241021_143000.zip")
    mp_id: str = Field(..., description="公众号ID", example="MP_WXS_3892772220")

@router.delete("/export/delete", summary="删除导出文件", response_model=BaseResponse)
async def delete_export_file(
    request: DeleteFileRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    删除指定的导出文件
    """
    try:
        # 参数验证
        if not request.filename :
            raise HTTPException(status_code=400, detail=error_response(40001, "文件名和公众号ID不能为空"))
        
        # 构建文件路径并做路径归一化及安全检测
        base_path = os.path.realpath(f"./data/docs/{request.mp_id}/")
        unsafe_path = os.path.join(base_path, request.filename)
        safe_path = os.path.realpath(os.path.normpath(unsafe_path))
        
        # 安全检查：确保文件在指定目录内，防止路径遍历攻击
        if not safe_path.startswith(base_path):
            raise HTTPException(status_code=403, detail=error_response(40301, "无权限删除该文件"))
        
        # 只允许删除.zip文件
        if not request.filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail=error_response(40001, "只能删除.zip格式的导出文件"))
        
        # 检查文件是否存在
        if not os.path.exists(safe_path):
            raise HTTPException(status_code=404, detail=error_response(40401, "文件不存在"))
        
        # 删除文件
        os.remove(safe_path)
        
        return success_response({
            "filename": request.filename,
            "message": "文件删除成功"
        })
        
    except PermissionError:
        raise HTTPException(status_code=403, detail=error_response(40301, "没有权限删除该文件"))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=error_response(42201, f"请求参数验证失败: {str(e)}"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=error_response(50000, f"删除文件失败: {str(e)}"))

# 兼容性接口：支持查询参数方式删除
@router.delete("/export/delete-by-query", summary="删除导出文件(查询参数)", response_model=BaseResponse)
async def delete_export_file_by_query(
    filename: str = Query(..., description="文件名"),
    mp_id: str = Query(..., description="公众号ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    删除指定的导出文件（通过查询参数）
    """
    # 创建请求对象并调用主删除函数
    request = DeleteFileRequest(filename=filename, mp_id=mp_id)
    return await delete_export_file(request, current_user)

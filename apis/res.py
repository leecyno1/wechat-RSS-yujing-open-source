from fastapi import APIRouter, Request, HTTPException
import httpx
from fastapi.responses import Response
import os
import hashlib
import time
import json
CACHE_DIR = "static/cache"
CACHE_TTL = 3600  # 缓存过期时间1小时

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

router = APIRouter(prefix="/res", tags=["资源反向代理"])
@router.api_route("/logo/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def reverse_proxy(request: Request, path: str):
    host="mmbiz.qpic.cn"
    domain=f"http://{host}"
    if not path.startswith(domain):
        raise HTTPException(status_code=403, detail=f"只允许 {domain} 开头的请求")
    
    # 生成缓存文件名
    cache_key = f"{request.method}_{path}".encode('utf-8')
    cache_filename = os.path.join(CACHE_DIR, hashlib.sha256(cache_key).hexdigest())
    
    # 检查缓存是否存在且有效
    if os.path.exists(cache_filename):
        file_mtime = os.path.getmtime(cache_filename)
        if time.time() - file_mtime < CACHE_TTL:
            with open(cache_filename, 'rb') as f:
                content = f.read()
            
            # 读取缓存的状态码和响应头
            headers_filename = cache_filename + ".headers"
            if os.path.exists(headers_filename):
                with open(headers_filename, 'r', encoding='utf-8') as f:
                    headers = json.load(f)
            else:
                headers = {}
            
            media_type = headers.get("Content-Type")
            status_code = 200  # 默认状态码
            
            return Response(
                content=content,
                status_code=status_code,
                headers=headers,
                media_type=media_type
            )
    
    target_url = path
    
    client = httpx.AsyncClient()
    request_data = await request.body()
    headers = dict(request.headers)
    headers.pop("host", host)
    headers.pop("referer", None)
    print(headers)
    resp = await client.request(
        method=request.method,
        url=target_url,
        # headers=headers,
        content=request_data
    )
    
    content = resp.content
    status_code = resp.status_code
    headers = dict(resp.headers)
    media_type = resp.headers.get("Content-Type")
    
    # 缓存响应
    with open(cache_filename, 'wb') as f:
        f.write(content)
    
    # 缓存响应头
    headers_filename = cache_filename + ".headers"
    with open(headers_filename, 'w', encoding='utf-8') as f:
        json.dump(headers, f)
    
    return Response(
        content=content,
        status_code=status_code,
        headers=headers,
        media_type=media_type
    )
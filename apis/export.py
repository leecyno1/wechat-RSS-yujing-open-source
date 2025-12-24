
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File,Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from core.auth import get_current_user
from core.db import DB
from core.wx import search_Biz
from .base import success_response, error_response
from datetime import datetime
from core.config import cfg
from core.res import save_avatar_locally
import csv
import io
import os
import uuid
import base64
from typing import Any, Optional
router = APIRouter(prefix=f"/export", tags=["导入/导出"])


def _safe_isoformat(dt: Any) -> str:
    if dt is None:
        return ""
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


def _normalize_fakeid(value: Optional[str]) -> str:
    if not value:
        return ""
    value = str(value).strip()
    if value.isdigit():
        return value
    try:
        decoded = base64.b64decode(value).decode("utf-8", errors="ignore").strip()
        return decoded if decoded.isdigit() else ""
    except Exception:
        return ""


@router.get("/mps/export", summary="导出公众号列表")
async def export_mps(
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        query = session.query(Feed)
        if kw:
            query = query.filter(Feed.mp_name.ilike(f"%{kw}%"))

        mps = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()

        # 准备CSV数据
        headers = ["id", "公众号名称", "封面图", "简介", "状态", "创建时间", "faker_id"]
        data = [[
            mp.id,
            mp.mp_name,
            mp.mp_cover,
            mp.mp_intro,
            mp.status,
            _safe_isoformat(mp.created_at),
            mp.faker_id
        ] for mp in mps]

        # 创建临时CSV文件
        temp_file = "temp_mp_export.csv"
        with open(temp_file, "w", encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(data)

        # 返回文件下载
        return FileResponse(
            temp_file,
            media_type="text/csv",
            filename="公众号列表.csv",
            background=BackgroundTask(lambda: os.remove(temp_file))
        )

    except Exception as e:
        print(f"导出公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="导出公众号列表失败"
            )
        )

@router.post("/mps/import", summary="导入公众号列表")
async def import_mps(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed

        # 读取上传的CSV文件
        contents = (await file.read()).decode('utf-8-sig')
        csv_reader = csv.DictReader(io.StringIO(contents))

        # 宽容兼容：至少要有「公众号名称」或「mp_name」
        if not csv_reader.fieldnames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40001, message="CSV文件为空或无法识别表头"),
            )
        has_name = ("公众号名称" in csv_reader.fieldnames) or ("mp_name" in csv_reader.fieldnames) or ("name" in csv_reader.fieldnames)
        if not has_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40001, message="CSV文件缺少必要列: 公众号名称/mp_name/name"),
            )

        # 导入数据
        imported = 0
        updated = 0
        skipped = 0

        for row in csv_reader:
            mp_name = (row.get("公众号名称") or row.get("mp_name") or row.get("name") or "").strip()
            if not mp_name:
                skipped += 1
                continue

            mp_cover = (row.get("封面图") or row.get("mp_cover") or row.get("avatar") or "").strip()
            mp_intro = (row.get("简介") or row.get("mp_intro") or row.get("description") or "").strip()
            status_val = int(row.get("状态", 1)) if row.get("状态") else 1
            faker_id = _normalize_fakeid(row.get("faker_id") or row.get("fakeid") or row.get("mp_id") or row.get("公众号ID") or "")
            mp_id = (row.get("id") or row.get("mpid") or "").strip()
            if not mp_id:
                mp_id = f"MP_WXS_{faker_id}" if faker_id else f"MP_WXS_{uuid.uuid4().hex[:12]}"

            # 检查是否已存在
            existing = None
            if faker_id:
                existing = session.query(Feed).filter(Feed.faker_id == faker_id).first()
            if not existing and mp_id:
                existing = session.query(Feed).filter(Feed.id == mp_id).first()

            if existing:
                # 更新现有记录
                existing.mp_name = mp_name or existing.mp_name
                existing.mp_cover = mp_cover or existing.mp_cover
                existing.mp_intro = mp_intro or existing.mp_intro
                existing.status = status_val
                if faker_id:
                    existing.faker_id = faker_id
                existing.updated_at = datetime.now()
                if not existing.created_at:
                    existing.created_at = existing.updated_at
                updated += 1
            else:
                # 创建新记录
                mp = Feed(
                    id=mp_id,
                    mp_name=mp_name,
                    mp_cover=mp_cover,
                    mp_intro=mp_intro,
                    status=status_val,
                    faker_id=faker_id,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                session.add(mp)
                imported += 1

        session.commit()

        return success_response({
            "message": "导入公众号列表成功",
            "stats": {
                "total": imported + updated + skipped,
                "imported": imported,
                "updated": updated,
                "skipped": skipped
            }
        })

    except Exception as e:
        session.rollback()
        print(f"导入公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="导入公众号列表失败"
            )
        )

@router.get("/mps/opml", summary="导出公众号列表为OPML格式")
async def export_mps_opml(
    request: Request,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        query = session.query(Feed)
        if kw:
            query = query.filter(Feed.mp_name.ilike(f"%{kw}%"))

        mps = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
        rss_domain=cfg.get("rss.base_url",str(request.base_url))
        if rss_domain=="":
            rss_domain=str(request.base_url)
        # 生成OPML内容
        opml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
  <head>
    <title>公众号订阅列表</title>
    <dateCreated>{date}</dateCreated>
  </head>
  <body>
{outlines}
  </body>
</opml>'''.format(
            date=datetime.now().isoformat(),
            outlines=''.join([f'<outline text="{mp.mp_name}" title="{mp.mp_name}" type="rss"  xmlUrl="{rss_domain}feed/{mp.id}.atom"/>\n' for mp in mps])
        )

        # 创建临时OPML文件
        temp_file = "temp_mp_export.opml"
        with open(temp_file, "w", encoding='utf-8') as f:
            f.write(opml_content)

        # 返回文件下载
        return FileResponse(
            temp_file,
            media_type="application/xml",
            filename="公众号订阅列表.opml",
            background=BackgroundTask(lambda: os.remove(temp_file))
        )

    except Exception as e:
        print(f"导出OPML列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50002,
                message="导出OPML列表失败"
            )
        )

@router.get("/tags", summary="导出标签列表")
async def export_tags(
        limit: int = Query(1000, ge=1, le=10000),
        offset: int = Query(0, ge=0),
        kw: str = Query(""),
        current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.tags import Tags
        query = session.query(Tags)
        if kw:
            query = query.filter(Tags.name.ilike(f"%{kw}%"))

        tags = query.order_by(Tags.created_at.desc()).limit(limit).offset(offset).all()

        headers = ["id", "标签名称", "封面图", "描述", "状态", "创建时间", "mps_id"]
        data = []
        for tag in tags:
            data.append([
                tag.id,
                tag.name,
                tag.cover,
                tag.intro,
                tag.status,
                tag.created_at.isoformat() if tag.created_at else "",
                tag.mps_id
            ])

        # 创建临时CSV文件
        temp_file = "temp_tags_export.csv"
        with open(temp_file, "w", encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(data)

        return FileResponse(
            temp_file,
            media_type="text/csv",
            filename="标签列表.csv",
            background=BackgroundTask(lambda: os.remove(temp_file))
        )

    except Exception as e:
        print(f"导出标签列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50003,
                message="导出标签列表失败"
            )
        )

@router.post("/tags/import", summary="导入标签列表")
async def import_tags(
        file: UploadFile = File(...),
        current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.tags import Tags

        contents = (await file.read()).decode('utf-8-sig')
        csv_reader = csv.DictReader(io.StringIO(contents))

        required_columns = ["标签名称", "状态", "mps_id"]
        if not all(col in csv_reader.fieldnames for col in required_columns):
            missing_cols = [col for col in required_columns if col not in csv_reader.fieldnames]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40002,
                    message=f"CSV文件缺少必要列: {', '.join(missing_cols)}"
                )
            )

        imported = 0
        updated = 0
        skipped = 0

        for row in csv_reader:
            tag_id = row.get("id")
            tag_name = row.get("标签名称")

            if not tag_name or not tag_name.strip():
                skipped += 1
                continue # 如果标签名称为空，则跳过此行

            existing_tag = None
            if tag_id and tag_id.strip():
                existing_tag = session.query(Tags).filter(Tags.id == tag_id.strip()).first()

            cover = row.get("封面图", "")
            intro = row.get("描述", "")
            try:
                status_val = int(row.get("状态", 1))
            except (ValueError, TypeError):
                status_val = 1
            mps_id_str = row.get("mps_id") or "[]"

            if existing_tag:
                existing_tag.name = tag_name
                existing_tag.cover = cover
                existing_tag.intro = intro
                existing_tag.status = status_val
                existing_tag.mps_id = mps_id_str
                existing_tag.updated_at = datetime.now()
                updated += 1
            else:
                new_tag = Tags(
                    id=str(uuid.uuid4()),
                    name=tag_name,
                    cover=cover,
                    intro=intro,
                    status=status_val,
                    mps_id=mps_id_str,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                session.add(new_tag)
                imported += 1

        session.commit()

        return success_response({
            "message": "导入标签列表成功",
            "stats": {
                "total_rows": imported + updated + skipped,
                "imported": imported,
                "updated": updated,
                "skipped": skipped
            }
        })

    except HTTPException as he:
        raise he
    except Exception as e:
        session.rollback()
        print(f"导入标签列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50004,
                message=f"导入标签列表失败: {str(e)}"
            )
        )

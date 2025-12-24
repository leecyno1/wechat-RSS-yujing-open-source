from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status as fast_status
from sqlalchemy import func

from apis.base import error_response, success_response
from core.auth import get_current_user
from core.db import DB
from core.insights import InsightsService
from core.models.article import Article
from core.models.article import ArticleBase
from core.models.base import DATA_STATUS
from core.models.feed import Feed
from driver.token import get as get_wx_cfg
import base64
import json
import requests
from core.config import cfg
from urllib.parse import urlparse


router = APIRouter(prefix="/channels", tags=["频道"])


def _safe_isoformat(dt):
    if dt is None:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)

def _normalize_fakeid(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip()
    # WeChat backend typically uses __biz (base64). Keep base64 when present.
    if v.isdigit():
        try:
            return base64.b64encode(v.encode("utf-8")).decode("utf-8")
        except Exception:
            return None
    try:
        decoded = base64.b64decode(v).decode("utf-8", errors="ignore").strip()
        return v if decoded.isdigit() else None
    except Exception:
        return None


def _normalize_title(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().split())


def _mp_url_key(url: str | None) -> str:
    """Best-effort key for matching WeChat article links."""
    if not url:
        return ""
    try:
        u = str(url).strip()
        if not u:
            return ""
        p = urlparse(u)
        path = (p.path or "").strip()
        if path.startswith("/s/"):
            return path.split("/s/", 1)[-1].strip()
        if path == "/s":
            parts: dict[str, str] = {}
            for kv in (p.query or "").split("&"):
                if not kv:
                    continue
                if "=" in kv:
                    k, v = kv.split("=", 1)
                else:
                    k, v = kv, ""
                parts.setdefault(k, v)
            if parts.get("sn"):
                return f"sn:{parts.get('sn')}"
            if parts.get("mid") and parts.get("idx"):
                return f"mididx:{parts.get('mid')}:{parts.get('idx')}"
        return ""
    except Exception:
        return ""


@router.get("/feeds", summary="获取频道(公众号)列表 + 未读统计")
async def list_channel_feeds(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    sort: str = Query("recent", description="recent|created|name"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()

    feed_query = session.query(Feed).filter(Feed.faker_id.isnot(None)).filter(Feed.faker_id != "")
    if kw:
        feed_query = feed_query.filter(Feed.mp_name.ilike(f"%{kw}%"))
    total = feed_query.count()

    # counts
    unread_rows = (
        session.query(ArticleBase.mp_id, func.count(ArticleBase.id))
        .filter(ArticleBase.status != DATA_STATUS.DELETED)
        .filter(ArticleBase.is_read == 0)
        .group_by(ArticleBase.mp_id)
        .all()
    )
    total_rows = (
        session.query(ArticleBase.mp_id, func.count(ArticleBase.id))
        .filter(ArticleBase.status != DATA_STATUS.DELETED)
        .group_by(ArticleBase.mp_id)
        .all()
    )
    latest_rows = (
        session.query(ArticleBase.mp_id, func.max(ArticleBase.publish_time))
        .filter(ArticleBase.status != DATA_STATUS.DELETED)
        .group_by(ArticleBase.mp_id)
        .all()
    )

    unread_map = {mp_id: int(cnt or 0) for mp_id, cnt in unread_rows}
    total_map = {mp_id: int(cnt or 0) for mp_id, cnt in total_rows}
    latest_map = {mp_id: int(ts or 0) for mp_id, ts in latest_rows}

    feeds = feed_query.all()

    # Normalize legacy faker_id (numeric) to base64 __biz, so mp.weixin backend list works reliably.
    try:
        dirty = False
        for f in feeds:
            norm = _normalize_fakeid(f.faker_id)
            if norm and f.faker_id != norm:
                f.faker_id = norm
                dirty = True
        if dirty:
            session.commit()
    except Exception:
        session.rollback()

    def sort_key(feed: Feed):
        if sort == "name":
            return (feed.mp_name or "")
        if sort == "created":
            return str(feed.created_at or "")
        # recent
        return latest_map.get(feed.id, 0)

    reverse = sort != "name"
    feeds_sorted = sorted(feeds, key=sort_key, reverse=reverse)
    feeds_page = feeds_sorted[offset : offset + limit]

    items = []
    for f in feeds_page:
        items.append(
            {
                "id": f.id,
                "name": f.mp_name or "",
                "cover": f.mp_cover or "",
                "intro": f.mp_intro or "",
                "created_at": _safe_isoformat(f.created_at),
                "unread_count": unread_map.get(f.id, 0),
                "article_count": total_map.get(f.id, 0),
                "latest_publish_time": latest_map.get(f.id, 0),
            }
        )

    stats = {
        "unread_total": int(sum(unread_map.values())),
        "article_total": int(sum(total_map.values())),
        "feed_total": int(total),
    }

    return success_response({"list": items, "total": total, "stats": stats, "page": {"limit": limit, "offset": offset, "total": total}})


@router.post("/read_all", summary="全部已读(按频道/关键词)")
async def mark_all_read(
    mp_id: str | None = Query(None, description="频道ID；为空表示全部"),
    kw: str = Query("", description="可选：仅标记标题包含关键词的文章"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    try:
        query = session.query(ArticleBase).filter(ArticleBase.status != DATA_STATUS.DELETED).filter(ArticleBase.is_read == 0)
        if mp_id:
            query = query.filter(ArticleBase.mp_id == mp_id)
        if kw:
            query = query.filter(ArticleBase.title.like(f"%{kw}%"))

        updated = query.update({"is_read": 1, "updated_at": datetime.now()}, synchronize_session=False)
        session.commit()
        return success_response({"updated": int(updated or 0)})
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"标记已读失败: {e}"),
        )


@router.post("/articles/{article_id}/backfill", summary="回填单篇文章摘要/封面(通过公众号后台接口)")
async def backfill_article_digest(
    article_id: str,
    max_pages: int = Query(25, ge=1, le=50, description="最多翻页数(每页5条)"),
    current_user: dict = Depends(get_current_user),
):
    """When an article was imported without digest/cover, backfill from mp.weixin backend list."""
    session = DB.get_session()
    article = session.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )
    if (article.description or "").strip():
        return success_response({"ok": True, "updated": False, "reason": "already_has_description"})

    feed = session.query(Feed).filter(Feed.id == article.mp_id).first()
    if not feed:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40402, message="公众号不存在"),
        )
    fakeid = _normalize_fakeid(feed.faker_id)
    if not fakeid:
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40001, message="该公众号缺少可用fakeid，无法回填"),
        )

    cookies = get_wx_cfg("cookie", "")
    token = get_wx_cfg("token", "")
    if not cookies or not token:
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40002, message="公众号平台未授权或会话缺失"),
        )

    # Extract the aid suffix to match returned items
    suffix = article_id.split("-", 1)[-1].strip()
    target_title = _normalize_title(article.title)
    target_key = _mp_url_key(article.url)
    url = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"

    headers = {
        "Cookie": cookies,
        "User-Agent": str(cfg.get("user_agent", "")) or "Mozilla/5.0",
        "Referer": "https://mp.weixin.qq.com/cgi-bin/appmsgpublish",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }

    for page in range(max_pages):
        params = {
            "sub": "list",
            "sub_action": "list_ex",
            "begin": str(page * 5),
            "count": "5",
            "fakeid": fakeid,
            "token": token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": 1,
        }
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            continue
        msg = resp.json() or {}
        base_resp = msg.get("base_resp") or {}
        if base_resp and int(base_resp.get("ret", 0) or 0) != 0:
            raise HTTPException(
                status_code=fast_status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40003,
                    message=f"公众号后台接口错误: {base_resp.get('err_msg','')} ({base_resp.get('ret')})",
                ),
            )
        if not msg or "publish_page" not in msg:
            continue
        try:
            publish_page = json.loads(msg.get("publish_page") or "{}")
        except Exception:
            publish_page = {}
        for pub in publish_page.get("publish_list", []) or []:
            try:
                info = json.loads(pub.get("publish_info") or "{}")
            except Exception:
                info = {}
            for item in info.get("appmsgex", []) or []:
                aid = str(item.get("aid") or item.get("id") or "").strip()
                if not aid:
                    continue
                matched_by = ""
                if aid == suffix:
                    matched_by = "aid"
                else:
                    item_key = _mp_url_key(item.get("link"))
                    item_title = _normalize_title(item.get("title"))
                    if target_key and item_key and target_key == item_key:
                        matched_by = "url_key"
                    elif target_title and item_title and target_title == item_title:
                        matched_by = "title"
                    else:
                        continue

                digest = (item.get("digest") or "").strip()
                cover = (item.get("cover") or "").strip()
                link = (item.get("link") or "").strip()

                if digest:
                    article.description = digest
                if cover and not (article.pic_url or "").strip():
                    article.pic_url = cover
                if link and not (article.url or "").strip():
                    article.url = link
                article.updated_at = datetime.now()
                session.add(article)
                session.commit()

                # refresh insight
                try:
                    InsightsService().get_or_create_basic(article_id)
                except Exception:
                    pass

                return success_response({"ok": True, "updated": True, "page": page, "matched_by": matched_by})

    return success_response(
        {
            "ok": False,
            "updated": False,
            "reason": "not_found_in_pages",
            "scanned_pages": int(max_pages),
            "target": {"article_id": article_id, "aid_suffix": suffix, "title": target_title, "url_key": target_key},
        }
    )


@router.post("/mps/{mp_id}/backfill", summary="批量回填某公众号的摘要/封面(最近N页)")
async def backfill_mp_recent_pages(
    mp_id: str,
    max_pages: int = Query(20, ge=1, le=100, description="最多翻页数(每页5条)"),
    only_missing: bool = Query(True, description="仅回填缺摘要/封面的文章"),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    feed = session.query(Feed).filter(Feed.id == mp_id).first()
    if not feed:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40402, message="公众号不存在"),
        )
    fakeid = _normalize_fakeid(feed.faker_id)
    if not fakeid:
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40001, message="该公众号缺少可用fakeid，无法回填"),
        )

    cookies = get_wx_cfg("cookie", "")
    token = get_wx_cfg("token", "")
    if not cookies or not token:
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40002, message="公众号平台未授权或会话缺失"),
        )

    from sqlalchemy import or_

    query = session.query(Article).filter(Article.mp_id == mp_id).filter(Article.status != DATA_STATUS.DELETED)
    if only_missing:
        query = query.filter(
            or_(
                Article.description.is_(None),
                Article.description == "",
                Article.pic_url.is_(None),
                Article.pic_url == "",
            )
        )
    articles = query.all()
    by_suffix: dict[str, Article] = {str(a.id).split("-", 1)[-1]: a for a in articles}

    url = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
    headers = {
        "Cookie": cookies,
        "User-Agent": str(cfg.get("user_agent", "")) or "Mozilla/5.0",
        "Referer": "https://mp.weixin.qq.com/cgi-bin/appmsgpublish",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }

    updated = 0
    matched_existing = 0
    scanned_items = 0
    updated_article_ids: list[str] = []

    for page in range(max_pages):
        params = {
            "sub": "list",
            "sub_action": "list_ex",
            "begin": str(page * 5),
            "count": "5",
            "fakeid": fakeid,
            "token": token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": 1,
        }
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            continue
        msg = resp.json() or {}
        base_resp = msg.get("base_resp") or {}
        if base_resp and int(base_resp.get("ret", 0) or 0) != 0:
            raise HTTPException(
                status_code=fast_status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40003,
                    message=f"公众号后台接口错误: {base_resp.get('err_msg','')} ({base_resp.get('ret')})",
                ),
            )
        if "publish_page" not in msg:
            break
        try:
            publish_page = json.loads(msg.get("publish_page") or "{}")
        except Exception:
            publish_page = {}

        for pub in publish_page.get("publish_list", []) or []:
            try:
                info = json.loads(pub.get("publish_info") or "{}")
            except Exception:
                info = {}
            for item in info.get("appmsgex", []) or []:
                aid = str(item.get("aid") or item.get("id") or "").strip()
                if not aid:
                    continue
                scanned_items += 1
                art = by_suffix.get(aid)
                if not art:
                    continue
                matched_existing += 1

                changed = False
                digest = (item.get("digest") or "").strip()
                cover = (item.get("cover") or "").strip()
                link = (item.get("link") or "").strip()

                if digest and not (art.description or "").strip():
                    art.description = digest
                    changed = True
                if cover and not (art.pic_url or "").strip():
                    art.pic_url = cover
                    changed = True
                if link and not (art.url or "").strip():
                    art.url = link
                    changed = True

                if changed:
                    art.updated_at = datetime.now()
                    session.add(art)
                    updated += 1
                    updated_article_ids.append(str(art.id))

        try:
            session.commit()
        except Exception:
            session.rollback()

    try:
        from core.queue import TaskQueue

        if updated_article_ids:
            service = InsightsService()
            for aid in updated_article_ids[:500]:
                TaskQueue.add_task(service.get_or_create_basic, aid)
    except Exception:
        pass

    return success_response(
        {
            "ok": True,
            "mp_id": mp_id,
            "max_pages": int(max_pages),
            "only_missing": bool(only_missing),
            "scanned_items": int(scanned_items),
            "matched_existing": int(matched_existing),
            "updated": int(updated),
        }
    )

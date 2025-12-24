import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status as fast_status

from apis.base import error_response, success_response, format_search_kw
from core.config import cfg
from core.db import DB
from core.insights import InsightsService
from core.models.article import Article, ArticleBase
from core.models.article_insight import ArticleInsight
from core.models.base import DATA_STATUS
from core.models.feed import Feed
from core.queue import TaskQueue


router = APIRouter(prefix="/service", tags=["Service API"])


def _parse_api_keys(raw: str) -> set[str]:
    keys: set[str] = set()
    for part in (raw or "").split(","):
        k = (part or "").strip()
        if k:
            keys.add(k)
    return keys


def require_service_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    raw = str(cfg.get("service.api_keys", "") or "")
    keys = _parse_api_keys(raw)
    if not keys:
        raise HTTPException(
            status_code=fast_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response(code=50301, message="Service API is disabled (set SERVICE_API_KEYS)."),
        )
    if not x_api_key or x_api_key not in keys:
        raise HTTPException(
            status_code=fast_status.HTTP_401_UNAUTHORIZED,
            detail=error_response(code=40111, message="Invalid X-API-Key."),
        )
    return x_api_key


def _estimate_word_count(text: str) -> int:
    if not text:
        return 0
    t = re.sub(r"\s+", "", text)
    return len(t)


def _serialize_feed(feed: Feed) -> dict:
    return {
        "id": str(feed.id),
        "name": feed.mp_name or "",
        "cover": feed.mp_cover or "",
        "intro": feed.mp_intro or "",
        "created_at": str(getattr(feed, "created_at", "") or ""),
        "updated_at": str(getattr(feed, "updated_at", "") or ""),
    }


def _serialize_insight(insight: ArticleInsight, *, include_llm: bool) -> dict:
    return {
        "article_id": insight.article_id,
        "summary": insight.summary or "",
        "headings": json.loads(insight.headings_json) if insight.headings_json else [],
        "key_points": json.loads(insight.key_points_json) if getattr(insight, "key_points_json", None) else None,
        "llm_breakdown": json.loads(insight.llm_breakdown_json) if (include_llm and insight.llm_breakdown_json) else None,
        "status": insight.status,
        "error": insight.error or "",
        "llm_provider": insight.llm_provider or "",
        "llm_model": insight.llm_model or "",
        "updated_at": str(getattr(insight, "updated_at", "") or ""),
        "created_at": str(getattr(insight, "created_at", "") or ""),
    }


@router.get("/ping", summary="Service API 健康检查")
async def service_ping(_key: str = Depends(require_service_api_key)):
    return success_response({"ok": True})


@router.get("/channels", summary="频道列表(公众号)")
async def service_list_channels(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()
    q = session.query(Feed).filter(Feed.faker_id.isnot(None)).filter(Feed.faker_id != "")
    if kw:
        q = q.filter(Feed.mp_name.ilike(f"%{kw}%"))
    total = q.count()
    rows = q.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
    return success_response({"list": [_serialize_feed(f) for f in rows], "total": total, "page": {"limit": limit, "offset": offset, "total": total}})


@router.get("/channels/{channel_id}/articles", summary="频道文章列表(按时间倒序)")
async def service_list_channel_articles(
    channel_id: str,
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str = Query(""),
    include_content: bool = Query(False),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()
    Art = Article if include_content else ArticleBase
    q = session.query(Art, Feed).join(Feed, Feed.id == Art.mp_id).filter(Art.status != DATA_STATUS.DELETED)
    if channel_id not in ("all", "", None):
        q = q.filter(Art.mp_id == channel_id)
    if search:
        q = q.filter(format_search_kw(search))
    total = q.count()
    rows = q.order_by(Art.publish_time.desc()).limit(limit).offset(offset).all()
    items = []
    for art, feed in rows:
        items.append(
            {
                "id": str(art.id),
                "title": art.title or "",
                "description": art.description or "",
                "publish_time": int(art.publish_time or 0),
                "mp_id": art.mp_id or "",
                "mp_name": feed.mp_name or "",
                "pic_url": art.pic_url or "",
                "url": art.url or "",
                "content": art.content if include_content else None,
                "word_count": _estimate_word_count((art.description or "") if not include_content else (art.content or art.description or "")),
            }
        )
    channel = None
    if channel_id not in ("all", "", None):
        f = session.query(Feed).filter(Feed.id == channel_id).first()
        channel = _serialize_feed(f) if f else None
    return success_response({"channel": channel, "list": items, "total": total, "page": {"limit": limit, "offset": offset, "total": total}})


@router.get("/articles/{article_id}", summary="文章详情(含洞察)")
async def service_get_article(
    article_id: str,
    include_content: bool = Query(True),
    include_llm: bool = Query(True),
    schedule_cache: bool = Query(True, description="缺失洞察时是否后台排队补齐"),
    _key: str = Depends(require_service_api_key),
):
    session = DB.get_session()
    art = session.query(Article).filter(Article.id == article_id).first()
    if not art or int(getattr(art, "status", 0) or 0) == int(DATA_STATUS.DELETED):
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )
    feed = session.query(Feed).filter(Feed.id == art.mp_id).first()
    service = InsightsService()
    insight = service.get_or_create_basic(article_id)
    if insight and schedule_cache:
        try:
            missing_kp = bool(cfg.get("insights.auto_key_points", True)) and not (getattr(insight, "key_points_json", None) or "")
            missing_bd = bool(cfg.get("insights.auto_llm_breakdown", False)) and include_llm and not (getattr(insight, "llm_breakdown_json", None) or "")
            if missing_kp or missing_bd:
                TaskQueue.add_task(service.ensure_cached, article_id)
        except Exception:
            pass

    out = {
        "id": str(art.id),
        "title": art.title or "",
        "description": art.description or "",
        "publish_time": int(art.publish_time or 0),
        "mp_id": art.mp_id or "",
        "pic_url": art.pic_url or "",
        "url": art.url or "",
        "content": art.content if include_content else None,
        "feed": _serialize_feed(feed) if feed else None,
        "insights": _serialize_insight(insight, include_llm=include_llm) if insight else None,
    }
    return success_response(out)


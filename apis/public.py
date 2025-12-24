import json
import re

from fastapi import APIRouter, HTTPException, Query, status as fast_status

from apis.base import error_response, success_response
from core.config import cfg
from core.db import DB
from core.insights import InsightsService
from core.models.article import Article
from core.models.feed import Feed
from core.models.article_insight import ArticleInsight
from core.insights.extract import html_to_text
from core.queue import TaskQueue


router = APIRouter(prefix="/public", tags=["公开"])


def _estimate_word_count(text: str) -> int:
    if not text:
        return 0
    t = re.sub(r"\s+", "", text)
    return len(t)


def _serialize_channel(feed: Feed) -> dict:
    return {
        "id": feed.id,
        "name": feed.mp_name or "",
        "cover": feed.mp_cover or "",
        "intro": feed.mp_intro or "",
    }


def _serialize_insight(insight: ArticleInsight) -> dict:
    return {
        "article_id": insight.article_id,
        "summary": insight.summary or "",
        "headings": json.loads(insight.headings_json) if insight.headings_json else [],
        "key_points": json.loads(insight.key_points_json) if getattr(insight, "key_points_json", None) else None,
        "llm_breakdown": None,  # public endpoints default to not returning full breakdown
        "status": insight.status,
        "error": insight.error or "",
        "updated_at": str(getattr(insight, "updated_at", "") or ""),
        "created_at": str(getattr(insight, "created_at", "") or ""),
    }


def _load_plaza_data() -> dict:
    import os
    import json

    path = str(cfg.get("plaza.file", "data/plaza_mps.json") or "data/plaza_mps.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("categories"), list):
                return data
    except Exception:
        pass
    return {"version": 1, "categories": []}


@router.get("/plaza", summary="公开订阅广场：分类推荐公众号")
async def public_plaza(kw: str = Query("", description="可选：关键词过滤"), limit: int = Query(500, ge=1, le=2000)):
    data = _load_plaza_data()
    q = (kw or "").strip().lower()
    if not q:
        return success_response(data)

    out = {"version": data.get("version", 1), "categories": []}
    for cat in data.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        items = []
        for it in cat.get("items") or []:
            if not isinstance(it, dict):
                continue
            hay = " ".join(
                [
                    str(it.get("name") or ""),
                    str(it.get("kw") or ""),
                    str(it.get("desc") or ""),
                    " ".join([str(x) for x in (it.get("tags") or [])]),
                ]
            ).lower()
            if q in hay:
                items.append(it)
            if len(items) >= limit:
                break
        if items:
            out["categories"].append({"id": cat.get("id"), "name": cat.get("name"), "items": items})
    return success_response(out)


@router.get("/channels", summary="公开频道列表(Feed)")
async def list_public_channels(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
):
    session = DB.get_session()
    query = session.query(Feed).filter(Feed.faker_id.isnot(None)).filter(Feed.faker_id != "")
    if kw:
        query = query.filter(Feed.mp_name.ilike(f"%{kw}%"))
    total = query.count()
    feeds = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
    return success_response(
        {
            "list": [_serialize_channel(f) for f in feeds],
            "total": total,
            "page": {"limit": limit, "offset": offset, "total": total},
        }
    )


@router.get("/channels/{channel_id}/articles", summary="公开频道文章列表(按时间倒序)")
async def list_public_channel_articles(
    channel_id: str,
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
):
    session = DB.get_session()

    query = session.query(Article, Feed).join(Feed, Feed.id == Article.mp_id)
    if channel_id not in ("all", "", None):
        query = query.filter(Article.mp_id == channel_id)
    if kw:
        from apis.base import format_search_kw

        query = query.filter(format_search_kw(kw))

    total = query.count()
    rows = query.order_by(Article.publish_time.desc()).limit(limit).offset(offset).all()

    items = []
    for article, feed in rows:
        text_for_count = html_to_text(article.content) or (article.description or "")
        items.append(
            {
                "id": str(article.id),
                "title": article.title or "",
                "description": article.description or "",
                "publish_time": int(article.publish_time or 0),
                "mp_id": article.mp_id or "",
                "mp_name": feed.mp_name or "",
                "pic_url": article.pic_url or "",
                "is_read": int(getattr(article, "is_read", 0) or 0),
                "word_count": _estimate_word_count(text_for_count),
            }
        )

    channel = None
    if channel_id not in ("all", "", None):
        feed = session.query(Feed).filter(Feed.id == channel_id).first()
        channel = _serialize_channel(feed) if feed else None

    return success_response(
        {
            "channel": channel,
            "list": items,
            "total": total,
            "page": {"limit": limit, "offset": offset, "total": total},
        }
    )


@router.get("/insights/{article_id}", summary="公开文章洞察(摘要/关键信息)")
async def get_public_insights(article_id: str):
    service = InsightsService()
    insight = service.get_or_create_basic(article_id)
    if not insight:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )

    # If caches missing, schedule background fill to improve browsing UX.
    try:
        auto_kp = bool(cfg.get("insights.auto_key_points", True))
        auto_bd = bool(cfg.get("insights.auto_llm_breakdown", False))
        if (auto_kp and not (getattr(insight, "key_points_json", None) or "")) or (auto_bd and not (getattr(insight, "llm_breakdown_json", None) or "")):
            TaskQueue.add_task(service.ensure_cached, article_id)
    except Exception:
        pass

    return success_response(_serialize_insight(insight))

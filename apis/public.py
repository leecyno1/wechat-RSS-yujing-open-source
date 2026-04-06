import json
import re

from fastapi import APIRouter, HTTPException, Query, status as fast_status
from sqlalchemy import and_, or_, func

from apis.base import error_response, success_response
from core.config import cfg
from core.db import DB
from core.insights import InsightsService
from core.models.article import Article
from core.models.feed import Feed
from core.models.article_insight import ArticleInsight
from core.models.user import User
from core.models.user_subscription import UserSubscription
from core.insights.extract import html_to_text
from core.queue import PriorityInsightsQueue


router = APIRouter(prefix="/public", tags=["公开"])


def _normalize_public_platform(raw: str | None, source_type: str | None = None, faker_id: str | None = None) -> str:
    p = str(raw or "").strip().lower()
    if not p:
        p = "wechat" if str(faker_id or "").strip() else str(source_type or "rss").strip().lower()
    if p == "wx":
        return "wechat"
    if p == "rsshub":
        return "rss"
    if p in {
        "wsj",
        "bbc",
        "nytimes",
        "guardian",
        "cnn",
        "npr",
        "cnbc",
        "global_news",
        "global_tech",
        "global_finance",
        "global_programming",
        "global_startups",
        "china_news",
        "china_tech",
        "china_finance",
        "china_product",
        "tech",
    }:
        return "portal"
    return p or "wechat"


def _estimate_word_count(text: str) -> int:
    if not text:
        return 0
    t = re.sub(r"\s+", "", text)
    return len(t)


def _serialize_channel(feed: Feed) -> dict:
    source_type = str(feed.source_type or "wechat")
    source_platform = _normalize_public_platform(
        str(feed.source_platform or ""),
        source_type,
        str(feed.faker_id or ""),
    )
    return {
        "id": feed.id,
        "name": feed.mp_name or "",
        "cover": feed.mp_cover or "",
        "intro": feed.mp_intro or "",
        "source_type": source_type,
        "source_platform": source_platform,
        "source_url": feed.source_url or "",
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
    supported_feed_filter = or_(
        and_(Feed.faker_id.isnot(None), Feed.faker_id != ""),
        Feed.source_type.in_(["rss", "rsshub"]),
    )
    query = session.query(Feed).filter(supported_feed_filter)
    using_admin_defaults = False

    # 游客默认展示 admin 当前订阅的全量来源（若存在），确保未登录视图与站点默认配置一致。
    try:
        admin_user = (
            session.query(User)
            .filter(func.lower(User.username) == "admin")
            .order_by(User.created_at.asc())
            .first()
        )
        admin_uid = str(getattr(admin_user, "id", "") or "").strip()
        if admin_uid:
            admin_query = (
                session.query(Feed)
                .join(UserSubscription, UserSubscription.feed_id == Feed.id)
                .filter(UserSubscription.user_id == admin_uid)
                .filter(supported_feed_filter)
            )
            if admin_query.first() is not None:
                query = admin_query
                using_admin_defaults = True
    except Exception:
        using_admin_defaults = False

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

    rows = (
        session.query(Article.mp_id, func.max(Article.publish_time).label("latest_publish_time"))
        .group_by(Article.mp_id)
        .all()
    )
    latest_publish_map = {str(mp_id): int(ts or 0) for mp_id, ts in rows if mp_id}

    def _feed_score(feed: Feed) -> int:
        fid = str(feed.id or "")
        latest_publish = int(latest_publish_map.get(fid, 0) or 0)
        update_time = int(getattr(feed, "update_time", 0) or 0)
        sync_time = int(getattr(feed, "sync_time", 0) or 0)
        created = 0
        try:
            created = int(feed.created_at.timestamp()) if getattr(feed, "created_at", None) else 0
        except Exception:
            created = 0
        return max(latest_publish, update_time, sync_time, created)

    if using_admin_defaults:
        feeds_all = query.all()
        feeds_all.sort(key=_feed_score, reverse=True)
        total = len(feeds_all)
        feeds = feeds_all[offset : offset + limit]
        return success_response(
            {
                "list": [_serialize_channel(f) for f in feeds],
                "total": total,
                "page": {"limit": limit, "offset": offset, "total": total, "default_mode": "admin_subscriptions"},
            }
        )

    # 回退模式：按平台推荐固定数量，避免首次进入“空平台/全量过多”。
    per_platform = max(1, min(10, int(cfg.get("public.default_per_platform", 3) or 3)))
    platform_order_raw = str(
        cfg.get(
            "public.platform_order",
            "wechat,zhihu,xueqiu,toutiao,baijiahao,weibo,portal,rss",
        )
        or "wechat,zhihu,xueqiu,toutiao,baijiahao,weibo,portal,rss"
    )
    platform_order = [x.strip().lower() for x in platform_order_raw.split(",") if x.strip()]
    if not platform_order:
        platform_order = ["wechat", "zhihu", "xueqiu", "toutiao", "baijiahao", "weibo", "portal", "rss"]

    feeds_all = query.order_by(Feed.created_at.desc()).all()
    by_platform: dict[str, list[Feed]] = {}
    for feed in feeds_all:
        p = _normalize_public_platform(str(feed.source_platform or ""), str(feed.source_type or ""), str(feed.faker_id or ""))
        if p not in platform_order:
            continue
        by_platform.setdefault(p, []).append(feed)

    selected: list[Feed] = []
    for p in platform_order:
        bucket = by_platform.get(p, [])
        if not bucket:
            continue
        bucket.sort(key=_feed_score, reverse=True)
        selected.extend(bucket[:per_platform])

    feeds = selected[offset : offset + limit]
    total = len(selected)
    return success_response(
        {
            "list": [_serialize_channel(f) for f in feeds],
            "total": total,
            "page": {"limit": limit, "offset": offset, "total": total, "default_mode": True},
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
                "source_platform": _normalize_public_platform(
                    str(feed.source_platform or ""),
                    str(feed.source_type or ""),
                    str(feed.faker_id or ""),
                ),
                "read_count": getattr(article, "read_count", None),
                "like_count": getattr(article, "like_count", None),
                "share_count": getattr(article, "share_count", None),
                "recommend_count": getattr(article, "recommend_count", None),
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


@router.get("/insights/{article_id:path}", summary="公开文章洞察(摘要/关键信息)")
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
            PriorityInsightsQueue.add_task(service.ensure_cached, article_id)
    except Exception:
        pass

    return success_response(_serialize_insight(insight))
